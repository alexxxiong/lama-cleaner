#!/usr/bin/env python3
import os
import hashlib

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import imghdr
import io
import multiprocessing
import random
import time
import uuid
from pathlib import Path
import signal
import sys
import logging

import cv2
import numpy as np
import torch
from PIL import Image
from lama_cleaner.logging_config import setup_logging, get_logger, show_startup_banner, log_shutdown, LoggerManager
from lama_cleaner.api_logging import init_api_logging, log_image_processing_start, log_image_processing_complete, log_image_processing_failed, log_model_switch
from lama_cleaner.performance_monitor import performance_monitor, track_performance, measure_performance
from lama_cleaner.error_tracker import ErrorContext, ErrorCategory, ErrorSeverity

from lama_cleaner.const import SD15_MODELS
from lama_cleaner.file_manager import FileManager
from lama_cleaner.model.utils import torch_gc
from lama_cleaner.model_manager import ModelManager
from lama_cleaner.plugins import (
    InteractiveSeg,
    RemoveBG,
    RealESRGANUpscaler,
    MakeGIF,
    GFPGANPlugin,
    RestoreFormerPlugin,
    AnimeSeg,
)
from lama_cleaner.schema import Config

try:
    torch._C._jit_override_can_fuse_on_cpu(False)
    torch._C._jit_override_can_fuse_on_gpu(False)
    torch._C._jit_set_texpr_fuser_enabled(False)
    torch._C._jit_set_nvfuser_enabled(False)
except:
    pass

from flask import (
    Flask,
    request,
    send_file,
    cli,
    make_response,
    send_from_directory,
    jsonify,
)
from flask_socketio import SocketIO

# Disable ability for Flask to display warning about using a development server in a production environment.
# https://gist.github.com/jerblack/735b9953ba1ab6234abb43174210d356
cli.show_server_banner = lambda *_: None
from flask_cors import CORS

from lama_cleaner.helper import (
    load_img,
    numpy_to_bytes,
    resize_max_size,
    pil_to_bytes,
)

NUM_THREADS = str(multiprocessing.cpu_count())

# fix libomp problem on windows https://github.com/Sanster/lama-cleaner/issues/56
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

os.environ["OMP_NUM_THREADS"] = NUM_THREADS
os.environ["OPENBLAS_NUM_THREADS"] = NUM_THREADS
os.environ["MKL_NUM_THREADS"] = NUM_THREADS
os.environ["VECLIB_MAXIMUM_THREADS"] = NUM_THREADS
os.environ["NUMEXPR_NUM_THREADS"] = NUM_THREADS
if os.environ.get("CACHE_DIR"):
    os.environ["TORCH_HOME"] = os.environ["CACHE_DIR"]

BUILD_DIR = os.environ.get("LAMA_CLEANER_BUILD_DIR", "app/build")


class NoFlaskwebgui(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "Running on http:" in msg:
            print(msg[msg.index("Running on http:") :])

        return (
            "flaskwebgui-keep-server-alive" not in msg
            and "socket.io" not in msg
            and "This is a development server." not in msg
        )


logging.getLogger("werkzeug").addFilter(NoFlaskwebgui())

app = Flask(__name__, static_folder=os.path.join(BUILD_DIR, "static"))
app.config["JSON_AS_ASCII"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "lama-cleaner-secret-key")
CORS(app, expose_headers=["Content-Disposition"])

# 初始化API日志中间件
init_api_logging(app)

sio_logger = logging.getLogger("sio-logger")
sio_logger.setLevel(logging.ERROR)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

model: ModelManager = None
thumb: FileManager = None
output_dir: str = None
device = None
input_image_path: str = None
is_disable_model_switch: bool = False
is_controlnet: bool = False
controlnet_method: str = "control_v11p_sd15_canny"
is_enable_file_manager: bool = False
is_enable_auto_saving: bool = False
is_desktop: bool = False
image_quality: int = 95
plugins = {}


def get_image_ext(img_bytes):
    w = imghdr.what("", img_bytes)
    if w is None:
        w = "jpeg"
    return w


def diffuser_callback(i, t, latents):
    socketio.emit("diffusion_progress", {"step": i})


@app.route("/save_image", methods=["POST"])
def save_image():
    if output_dir is None:
        return "--output-dir is None", 500

    input = request.files
    filename = request.form["filename"]
    origin_image_bytes = input["image"].read()  # RGB
    ext = get_image_ext(origin_image_bytes)
    image, alpha_channel, exif_infos = load_img(origin_image_bytes, return_exif=True)
    save_path = os.path.join(output_dir, filename)

    if alpha_channel is not None:
        if alpha_channel.shape[:2] != image.shape[:2]:
            alpha_channel = cv2.resize(
                alpha_channel, dsize=(image.shape[1], image.shape[0])
            )
        image = np.concatenate((image, alpha_channel[:, :, np.newaxis]), axis=-1)

    pil_image = Image.fromarray(image)

    img_bytes = pil_to_bytes(
        pil_image,
        ext,
        quality=image_quality,
        exif_infos=exif_infos,
    )
    with open(save_path, "wb") as fw:
        fw.write(img_bytes)

    return "ok", 200


@app.route("/medias/<tab>")
def medias(tab):
    if tab == "image":
        response = make_response(jsonify(thumb.media_names), 200)
    else:
        response = make_response(jsonify(thumb.output_media_names), 200)
    # response.last_modified = thumb.modified_time[tab]
    # response.cache_control.no_cache = True
    # response.cache_control.max_age = 0
    # response.make_conditional(request)
    return response


@app.route("/media/<tab>/<filename>")
def media_file(tab, filename):
    if tab == "image":
        return send_from_directory(thumb.root_directory, filename)
    return send_from_directory(thumb.output_dir, filename)


@app.route("/media_thumbnail/<tab>/<filename>")
def media_thumbnail_file(tab, filename):
    args = request.args
    width = args.get("width")
    height = args.get("height")
    if width is None and height is None:
        width = 256
    if width:
        width = int(float(width))
    if height:
        height = int(float(height))

    directory = thumb.root_directory
    if tab == "output":
        directory = thumb.output_dir
    thumb_filename, (width, height) = thumb.get_thumbnail(
        directory, filename, width, height
    )
    thumb_filepath = f"{app.config['THUMBNAIL_MEDIA_THUMBNAIL_ROOT']}{thumb_filename}"

    response = make_response(send_file(thumb_filepath))
    response.headers["X-Width"] = str(width)
    response.headers["X-Height"] = str(height)
    return response


@app.route("/inpaint", methods=["POST"])
@track_performance("image_inpainting")
def process():
    # 生成任务ID用于追踪
    task_id = str(uuid.uuid4())[:8]
    
    input = request.files
    # RGB
    origin_image_bytes = input["image"].read()
    image, alpha_channel, exif_infos = load_img(origin_image_bytes, return_exif=True)

    mask, _ = load_img(input["mask"].read(), gray=True)
    mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]

    if image.shape[:2] != mask.shape[:2]:
        return (
            f"Mask shape{mask.shape[:2]} not queal to Image shape{image.shape[:2]}",
            400,
        )

    original_shape = image.shape
    interpolation = cv2.INTER_CUBIC

    form = request.form
    size_limit = max(image.shape)
    
    # 记录图像处理开始
    log_image_processing_start(
        task_id=task_id,
        image_path=f"upload_{len(origin_image_bytes)}bytes",
        processing_type="inpainting"
    )

    if "paintByExampleImage" in input:
        paint_by_example_example_image, _ = load_img(
            input["paintByExampleImage"].read()
        )
        paint_by_example_example_image = Image.fromarray(paint_by_example_example_image)
    else:
        paint_by_example_example_image = None

    config = Config(
        ldm_steps=form["ldmSteps"],
        ldm_sampler=form["ldmSampler"],
        hd_strategy=form["hdStrategy"],
        zits_wireframe=form["zitsWireframe"],
        hd_strategy_crop_margin=form["hdStrategyCropMargin"],
        hd_strategy_crop_trigger_size=form["hdStrategyCropTrigerSize"],
        hd_strategy_resize_limit=form["hdStrategyResizeLimit"],
        prompt=form["prompt"],
        negative_prompt=form["negativePrompt"],
        use_croper=form["useCroper"],
        croper_x=form["croperX"],
        croper_y=form["croperY"],
        croper_height=form["croperHeight"],
        croper_width=form["croperWidth"],
        sd_scale=form["sdScale"],
        sd_mask_blur=form["sdMaskBlur"],
        sd_strength=form["sdStrength"],
        sd_steps=form["sdSteps"],
        sd_guidance_scale=form["sdGuidanceScale"],
        sd_sampler=form["sdSampler"],
        sd_seed=form["sdSeed"],
        sd_match_histograms=form["sdMatchHistograms"],
        cv2_flag=form["cv2Flag"],
        cv2_radius=form["cv2Radius"],
        paint_by_example_steps=form["paintByExampleSteps"],
        paint_by_example_guidance_scale=form["paintByExampleGuidanceScale"],
        paint_by_example_mask_blur=form["paintByExampleMaskBlur"],
        paint_by_example_seed=form["paintByExampleSeed"],
        paint_by_example_match_histograms=form["paintByExampleMatchHistograms"],
        paint_by_example_example_image=paint_by_example_example_image,
        p2p_steps=form["p2pSteps"],
        p2p_image_guidance_scale=form["p2pImageGuidanceScale"],
        p2p_guidance_scale=form["p2pGuidanceScale"],
        controlnet_conditioning_scale=form["controlnet_conditioning_scale"],
        controlnet_method=form["controlnet_method"],
    )

    if config.sd_seed == -1:
        config.sd_seed = random.randint(1, 999999999)
    if config.paint_by_example_seed == -1:
        config.paint_by_example_seed = random.randint(1, 999999999)

    logger.info(f"Origin image shape: {original_shape}")
    image = resize_max_size(image, size_limit=size_limit, interpolation=interpolation)

    mask = resize_max_size(mask, size_limit=size_limit, interpolation=interpolation)

    start = time.time()
    try:
        res_np_img = model(image, mask, config)
        processing_time = time.time() - start
        
        # 记录处理成功
        log_image_processing_complete(
            task_id=task_id,
            processing_time=processing_time,
            output_path=f"result_{res_np_img.shape}"
        )
        
    except RuntimeError as e:
        processing_time = time.time() - start
        error_msg = str(e)
        
        # 记录处理失败
        log_image_processing_failed(task_id=task_id, error=error_msg)
        
        # 追踪错误
        log_manager = LoggerManager()
        error_id = log_manager.track_error(
            e,
            operation="image_inpainting",
            task_id=task_id,
            model=model.name,
            image_size=str(image.shape) if hasattr(image, 'shape') else 'unknown'
        )
        
        if "CUDA out of memory. " in error_msg:
            # NOTE: the string may change?
            return "CUDA out of memory", 500
        else:
            logger.exception(e)
            return f"{error_msg} (Error ID: {error_id})", 500
    finally:
        logger.info(f"process time: {(time.time() - start) * 1000}ms")
        torch_gc()

    res_np_img = cv2.cvtColor(res_np_img.astype(np.uint8), cv2.COLOR_BGR2RGB)
    if alpha_channel is not None:
        if alpha_channel.shape[:2] != res_np_img.shape[:2]:
            alpha_channel = cv2.resize(
                alpha_channel, dsize=(res_np_img.shape[1], res_np_img.shape[0])
            )
        res_np_img = np.concatenate(
            (res_np_img, alpha_channel[:, :, np.newaxis]), axis=-1
        )

    ext = get_image_ext(origin_image_bytes)

    bytes_io = io.BytesIO(
        pil_to_bytes(
            Image.fromarray(res_np_img),
            ext,
            quality=image_quality,
            exif_infos=exif_infos,
        )
    )

    response = make_response(
        send_file(
            # io.BytesIO(numpy_to_bytes(res_np_img, ext)),
            bytes_io,
            mimetype=f"image/{ext}",
        )
    )
    response.headers["X-Seed"] = str(config.sd_seed)

    socketio.emit("diffusion_finish")
    return response


@app.route("/run_plugin", methods=["POST"])
@track_performance("plugin_execution")
def run_plugin():
    form = request.form
    files = request.files
    name = form["name"]
    if name not in plugins:
        return "Plugin not found", 500

    origin_image_bytes = files["image"].read()  # RGB
    rgb_np_img, alpha_channel, exif_infos = load_img(
        origin_image_bytes, return_exif=True
    )

    start = time.time()
    try:
        form = dict(form)
        if name == InteractiveSeg.name:
            img_md5 = hashlib.md5(origin_image_bytes).hexdigest()
            form["img_md5"] = img_md5
        bgr_res = plugins[name](rgb_np_img, files, form)
    except RuntimeError as e:
        torch.cuda.empty_cache()
        if "CUDA out of memory. " in str(e):
            # NOTE: the string may change?
            return "CUDA out of memory", 500
        else:
            logger.exception(e)
            return "Internal Server Error", 500

    logger.info(f"{name} process time: {(time.time() - start) * 1000}ms")
    torch_gc()

    if name == MakeGIF.name:
        return send_file(
            io.BytesIO(bgr_res),
            mimetype="image/gif",
            as_attachment=True,
            download_name=form["filename"],
        )
    if name == InteractiveSeg.name:
        return make_response(
            send_file(
                io.BytesIO(numpy_to_bytes(bgr_res, "png")),
                mimetype="image/png",
            )
        )

    if name in [RemoveBG.name, AnimeSeg.name]:
        rgb_res = bgr_res
        ext = "png"
    else:
        rgb_res = cv2.cvtColor(bgr_res, cv2.COLOR_BGR2RGB)
        ext = get_image_ext(origin_image_bytes)
        if alpha_channel is not None:
            if alpha_channel.shape[:2] != rgb_res.shape[:2]:
                alpha_channel = cv2.resize(
                    alpha_channel, dsize=(rgb_res.shape[1], rgb_res.shape[0])
                )
            rgb_res = np.concatenate(
                (rgb_res, alpha_channel[:, :, np.newaxis]), axis=-1
            )

    response = make_response(
        send_file(
            io.BytesIO(
                pil_to_bytes(
                    Image.fromarray(rgb_res),
                    ext,
                    quality=image_quality,
                    exif_infos=exif_infos,
                )
            ),
            mimetype=f"image/{ext}",
        )
    )
    return response


@app.route("/server_config", methods=["GET"])
def get_server_config():
    return {
        "isControlNet": is_controlnet,
        "controlNetMethod": controlnet_method,
        "isDisableModelSwitchState": is_disable_model_switch,
        "isEnableAutoSaving": is_enable_auto_saving,
        "enableFileManager": is_enable_file_manager,
        "plugins": list(plugins.keys()),
    }, 200


@app.route("/model")
def current_model():
    return model.name, 200


@app.route("/model_downloaded/<name>")
def model_downloaded(name):
    return str(model.is_downloaded(name)), 200


@app.route("/is_desktop")
def get_is_desktop():
    return str(is_desktop), 200


@app.route("/model", methods=["POST"])
@track_performance("model_switch")
def switch_model():
    if is_disable_model_switch:
        return "Switch model is disabled", 400

    new_name = request.form.get("name")
    if new_name == model.name:
        return "Same model", 200

    old_name = model.name
    start_time = time.time()
    
    try:
        model.switch(new_name)
        switch_time = time.time() - start_time
        
        # 记录模型切换成功
        log_model_switch(old_name, new_name, switch_time)
        
    except NotImplementedError:
        return f"{new_name} not implemented", 403
    return f"ok, switch to {new_name}", 200


@app.route("/")
def index():
    return send_file(os.path.join(BUILD_DIR, "index.html"))


@app.route("/inputimage")
def set_input_photo():
    if input_image_path:
        with open(input_image_path, "rb") as f:
            image_in_bytes = f.read()
        return send_file(
            input_image_path,
            as_attachment=True,
            download_name=Path(input_image_path).name,
            mimetype=f"image/{get_image_ext(image_in_bytes)}",
        )
    else:
        return "No Input Image"


def build_plugins(args):
    global plugins
    if args.enable_interactive_seg:
        logger.info(f"🔌 初始化插件: {InteractiveSeg.name}")
        plugins[InteractiveSeg.name] = InteractiveSeg(
            args.interactive_seg_model, args.interactive_seg_device
        )

    if args.enable_remove_bg:
        logger.info(f"🔌 初始化插件: {RemoveBG.name}")
        plugins[RemoveBG.name] = RemoveBG()

    if args.enable_anime_seg:
        logger.info(f"🔌 初始化插件: {AnimeSeg.name}")
        plugins[AnimeSeg.name] = AnimeSeg()

    if args.enable_realesrgan:
        logger.info(
            f"Initialize {RealESRGANUpscaler.name} plugin: {args.realesrgan_model}, {args.realesrgan_device}"
        )
        plugins[RealESRGANUpscaler.name] = RealESRGANUpscaler(
            args.realesrgan_model,
            args.realesrgan_device,
            no_half=args.realesrgan_no_half,
        )

    if args.enable_gfpgan:
        logger.info(f"🔌 初始化插件: {GFPGANPlugin.name}")
        if args.enable_realesrgan:
            logger.info("Use realesrgan as GFPGAN background upscaler")
        else:
            logger.info(
                f"GFPGAN no background upscaler, use --enable-realesrgan to enable it"
            )
        plugins[GFPGANPlugin.name] = GFPGANPlugin(
            args.gfpgan_device, upscaler=plugins.get(RealESRGANUpscaler.name, None)
        )

    if args.enable_restoreformer:
        logger.info(f"🔌 初始化插件: {RestoreFormerPlugin.name}")
        plugins[RestoreFormerPlugin.name] = RestoreFormerPlugin(
            args.restoreformer_device,
            upscaler=plugins.get(RealESRGANUpscaler.name, None),
        )

    if args.enable_gif:
        logger.info("🔌 初始化插件: GIF Maker")
        plugins[MakeGIF.name] = MakeGIF()


def main(args):
    global model
    global device
    global input_image_path
    global is_disable_model_switch
    global is_enable_file_manager
    global is_desktop
    global thumb
    global output_dir
    global is_enable_auto_saving
    global is_controlnet
    global controlnet_method
    global image_quality
    
    # 设置日志系统
    setup_logging(level="INFO")
    logger = get_logger("server")
    
    # 检查是否启用分布式模式
    if hasattr(args, 'distributed') and args.distributed:
        logger.info("🚀 启动分布式调度器...")
        from lama_cleaner.distributed.scheduler import DistributedScheduler
        
        # 设置环境变量
        os.environ['LAMA_CLEANER_DISTRIBUTED'] = 'true'
        
        # 显示启动横幅
        show_startup_banner(
            version="1.0.0",
            mode="分布式调度器",
            host=args.host,
            port=args.port
        )
        
        # 启动调度器
        scheduler = DistributedScheduler()
        scheduler.start()
        return
    
    # 显示启动横幅
    show_startup_banner(
        version="1.0.0",
        mode="Web 服务器",
        host=args.host,
        port=args.port
    )
    
    # 注册优雅关闭处理器
    def signal_handler(signum, frame):
        logger.info("收到停止信号，正在优雅关闭...")
        log_shutdown("server")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    build_plugins(args)

    image_quality = args.quality

    if args.sd_controlnet and args.model in SD15_MODELS:
        is_controlnet = True
        controlnet_method = args.sd_controlnet_method

    output_dir = args.output_dir
    if output_dir:
        is_enable_auto_saving = True

    device = torch.device(args.device)
    is_disable_model_switch = args.disable_model_switch
    is_desktop = args.gui
    if is_disable_model_switch:
        logger.info(
            "🔒 模型切换已禁用 (--disable-model-switch)"
        )

    if args.input and os.path.isdir(args.input):
        logger.info("📁 初始化文件管理器")
        thumb = FileManager(app)
        is_enable_file_manager = True
        app.config["THUMBNAIL_MEDIA_ROOT"] = args.input
        app.config["THUMBNAIL_MEDIA_THUMBNAIL_ROOT"] = os.path.join(
            args.output_dir, "lama_cleaner_thumbnails"
        )
        thumb.output_dir = Path(args.output_dir)
        # thumb.start()
        # try:
        #     while True:
        #         time.sleep(1)
        # finally:
        #     thumb.image_dir_observer.stop()
        #     thumb.image_dir_observer.join()
        #     thumb.output_dir_observer.stop()
        #     thumb.output_dir_observer.join()

    else:
        input_image_path = args.input

    model = ModelManager(
        name=args.model,
        sd_controlnet=args.sd_controlnet,
        sd_controlnet_method=args.sd_controlnet_method,
        device=device,
        no_half=args.no_half,
        hf_access_token=args.hf_access_token,
        disable_nsfw=args.sd_disable_nsfw or args.disable_nsfw,
        sd_cpu_textencoder=args.sd_cpu_textencoder,
        sd_run_local=args.sd_run_local,
        sd_local_model_path=args.sd_local_model_path,
        local_files_only=args.local_files_only,
        cpu_offload=args.cpu_offload,
        enable_xformers=args.sd_enable_xformers or args.enable_xformers,
        callback=diffuser_callback,
    )

    if args.gui:
        app_width, app_height = args.gui_size
        from flaskwebgui import FlaskUI

        ui = FlaskUI(
            app,
            socketio=socketio,
            width=app_width,
            height=app_height,
            host=args.host,
            port=args.port,
            close_server_on_exit=not args.no_gui_auto_close,
        )
        ui.run()
    else:
        socketio.run(
            app,
            host=args.host,
            port=args.port,
            debug=args.debug,
            allow_unsafe_werkzeug=True,
        )

if __name__ == "__main__":
    from lama_cleaner.parse_args import parse_args
    args = parse_args()
    main(args)
