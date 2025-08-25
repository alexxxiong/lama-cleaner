# Technology Stack

## Backend
- **Python 3.9-3.10** (required version range)
- **Flask 2.2.3** - Web framework
- **Flask-SocketIO** - Real-time communication
- **PyTorch** - Deep learning framework
- **Transformers 4.27.4** - Hugging Face transformers
- **Diffusers 0.16.1** - Stable Diffusion pipeline
- **OpenCV** - Image processing
- **PIL/Pillow** - Image manipulation
- **NumPy** - Numerical operations

## Frontend
- **React 17** with TypeScript
- **Recoil** - State management
- **Radix UI** - Component library
- **Tailwind CSS** - Styling
- **SCSS/Sass** - CSS preprocessing
- **i18next** - Internationalization
- **Socket.IO Client** - Real-time communication
- **pnpm** - Package manager

## Build System
- **Webpack 5** - Module bundler
- **Babel** - JavaScript transpiler
- **ESLint + Prettier** - Code formatting and linting
- **Jest** - Testing framework

## Development Commands

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m lama_cleaner --model=lama --device=cpu --port=8080

# Run with GPU support
pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cu117
python -m lama_cleaner --model=lama --device=cuda --port=8080
```

### Frontend
```bash
# Navigate to frontend directory
cd lama_cleaner/app/

# Install dependencies
pnpm install

# Start development server
pnpm start

# Build for production
pnpm build

# Run tests
pnpm test
```

### Docker
```bash
# Build CPU image
docker buildx build -f ./docker/CPUDockerfile -t lama-cleaner:cpu .

# Build GPU image
docker buildx build -f ./docker/GPUDockerfile -t lama-cleaner:gpu .
```

## Key Dependencies
- **controlnet-aux** - ControlNet preprocessing
- **gradio** - Alternative UI framework
- **loguru** - Enhanced logging
- **safetensors** - Safe tensor serialization
- **omegaconf** - Configuration management