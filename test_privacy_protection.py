#!/usr/bin/env python3
"""
隐私保护系统测试脚本
测试日志脱敏、访问控制和隐私保护功能
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from lama_cleaner.logging_config import LoggerManager
from lama_cleaner.privacy_protector import (
    PrivacyConfig,
    privacy_protector,
    SensitiveDataDetector,
    DataMasker
)
from loguru import logger


def test_sensitive_data_detection():
    """测试敏感数据检测"""
    logger.info("\n📌 测试1: 敏感数据检测")
    
    detector = SensitiveDataDetector()
    
    test_texts = [
        "用户邮箱是 john.doe@example.com",
        "电话号码: +86-138-1234-5678",
        "IP地址: 192.168.1.100",
        "信用卡: 4111-1111-1111-1111",
        "API密钥: sk_test_XXXXXXXXXXXXXXXXXXXX",
        "访问令牌: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "文件路径: /Users/johndoe/Documents/secret.txt",
        "数据库连接: postgres://user:password@localhost:5432/mydb"
    ]
    
    for text in test_texts:
        detected = detector.detect(text)
        if detected:
            logger.info(f"✅ 检测到敏感数据: {text[:50]}...")
            for data_type, matches in detected.items():
                logger.info(f"  • {data_type.value}: {matches}")
        else:
            logger.warning(f"⚠️ 未检测到敏感数据: {text[:50]}...")


def test_data_masking():
    """测试数据脱敏"""
    logger.info("\n📌 测试2: 数据脱敏")
    
    config = PrivacyConfig()
    masker = DataMasker(config)
    
    # 测试邮箱脱敏
    email = "john.doe@example.com"
    masked_email = masker.mask_email(email)
    logger.info(f"邮箱脱敏: {email} → {masked_email}")
    
    # 测试电话脱敏
    phone = "+86-138-1234-5678"
    masked_phone = masker.mask_phone(phone)
    logger.info(f"电话脱敏: {phone} → {masked_phone}")
    
    # 测试IP脱敏
    ip = "192.168.1.100"
    masked_ip = masker.mask_ip(ip)
    logger.info(f"IP脱敏: {ip} → {masked_ip}")
    
    # 测试信用卡脱敏
    cc = "4111-1111-1111-1111"
    masked_cc = masker.mask_credit_card(cc)
    logger.info(f"信用卡脱敏: {cc} → {masked_cc}")
    
    # 测试路径脱敏
    path = "/Users/johndoe/Documents/secret.txt"
    masked_path = masker.mask_path(path)
    logger.info(f"路径脱敏: {path} → {masked_path}")


def test_text_masking():
    """测试文本整体脱敏"""
    logger.info("\n📌 测试3: 文本整体脱敏")
    
    config = PrivacyConfig()
    masker = DataMasker(config)
    
    text = """
    用户信息:
    - 邮箱: alice@company.com
    - 电话: 13812345678
    - IP地址: 10.0.0.50
    - 文件位置: /Users/alice/private/data.csv
    - API密钥: sk_live_XXXXXXXXXXXXXXXXXXXX
    """
    
    logger.info("原始文本:")
    logger.info(text)
    
    masked_text = masker.mask_text(text)
    logger.info("\n脱敏后文本:")
    logger.info(masked_text)


def test_dict_masking():
    """测试字典数据脱敏"""
    logger.info("\n📌 测试4: 字典数据脱敏")
    
    config = PrivacyConfig()
    masker = DataMasker(config)
    
    data = {
        "user_email": "bob@example.org",
        "password": "super_secret_123",
        "api_key": "sk_test_XXXXXXXXX",
        "phone_number": "555-123-4567",
        "ip_address": "192.168.0.1",
        "database_url": "mysql://root:password@localhost/db",
        "config": {
            "secret_key": "my_secret_key",
            "token": "Bearer abc123xyz",
            "user_path": "/Users/bob/workspace"
        }
    }
    
    logger.info("原始数据:")
    for key, value in data.items():
        logger.info(f"  {key}: {value}")
    
    masked_data = masker.mask_dict(data)
    logger.info("\n脱敏后数据:")
    for key, value in masked_data.items():
        logger.info(f"  {key}: {value}")


def test_access_control():
    """测试访问控制"""
    logger.info("\n📌 测试5: 访问控制")
    
    # 添加不同角色的用户
    privacy_protector.access_controller.add_user("admin_user", "admin")
    privacy_protector.access_controller.add_user("dev_user", "developer")
    privacy_protector.access_controller.add_user("view_user", "viewer")
    privacy_protector.access_controller.add_user("audit_user", "auditor")
    
    # 测试不同用户的权限
    users_actions = [
        ("admin_user", ["read", "write", "delete", "export"]),
        ("dev_user", ["read", "write", "export"]),
        ("view_user", ["read"]),
        ("audit_user", ["read", "export"])
    ]
    
    for user, actions in users_actions:
        logger.info(f"\n用户 {user} (角色: {privacy_protector.access_controller.get_user_role(user)}):")
        for action in ["read", "write", "delete", "export"]:
            has_permission = privacy_protector.check_access(user, action)
            emoji = "✅" if has_permission else "❌"
            logger.info(f"  {emoji} {action}: {'允许' if has_permission else '拒绝'}")


def test_logger_with_privacy():
    """测试带隐私保护的日志记录"""
    logger.info("\n📌 测试6: 带隐私保护的日志记录")
    
    # 初始化带隐私保护的日志管理器
    log_manager = LoggerManager()
    log_manager.setup_logging(level="INFO", enable_file_logging=False)
    
    # 启用隐私保护
    log_manager.enable_privacy_protection()
    
    # 记录包含敏感信息的日志
    logger.info("用户 john@example.com 从 IP 192.168.1.100 登录")
    logger.info("处理文件: /Users/john/Documents/confidential.pdf")
    logger.info("数据库连接: postgres://admin:password123@db.example.com:5432/myapp")
    logger.warning("API密钥泄露风险: sk_live_XXXXXXXXXXXXXXXXXXXX")
    
    # 测试数据保护
    sensitive_data = {
        "user_id": "12345",
        "email": "user@example.com",
        "password": "secret123",
        "credit_card": "4111111111111111",
        "ssn": "123-45-6789"
    }
    
    protected_data = log_manager.protect_log_data(sensitive_data)
    logger.info(f"保护后的数据: {protected_data}")


def test_privacy_configuration():
    """测试隐私配置"""
    logger.info("\n📌 测试7: 隐私配置")
    
    log_manager = LoggerManager()
    
    # 配置隐私选项
    log_manager.configure_privacy(
        mask_emails=True,
        mask_phones=False,
        mask_ips=True,
        hash_usernames=False,
        remove_image_data=True
    )
    
    # 获取隐私报告
    report = log_manager.get_privacy_report()
    
    logger.info("隐私保护配置:")
    config = report['config']
    logger.info(f"  • 脱敏已启用: {config['masking_enabled']}")
    logger.info(f"  • 脱敏类型: {[t for t in config['masked_types'] if t]}")
    logger.info(f"  • 敏感键数量: {len(config['sensitive_keys'])}")
    
    logger.info("\n访问控制配置:")
    ac = report['access_control']
    for role, permissions in ac['roles'].items():
        logger.info(f"  • {role}: {permissions}")
    
    logger.info(f"\n审计摘要:")
    audit = report['audit_summary']
    logger.info(f"  • 总访问检查: {audit['total_access_checks']}")
    logger.info(f"  • 允许次数: {audit['granted']}")
    logger.info(f"  • 拒绝次数: {audit['denied']}")


def test_audit_log():
    """测试审计日志"""
    logger.info("\n📌 测试8: 审计日志")
    
    log_manager = LoggerManager()
    
    # 模拟一些访问检查
    test_users = ["user1", "user2", "admin"]
    test_actions = ["read", "write", "delete"]
    
    for user in test_users:
        # 添加用户
        role = "admin" if user == "admin" else "viewer"
        log_manager.add_log_user(user, role)
        
        # 测试访问
        for action in test_actions:
            log_manager.check_log_access(user, action)
    
    # 获取审计日志
    audit_logs = log_manager.get_audit_log(limit=10)
    
    logger.info(f"审计日志 (最近{len(audit_logs)}条):")
    for log in audit_logs[-5:]:  # 显示最后5条
        emoji = "✅" if log['granted'] else "❌"
        logger.info(f"  {emoji} {log['user_id']} → {log['action']}: {'允许' if log['granted'] else '拒绝'}")


def test_image_data_removal():
    """测试图像数据移除"""
    logger.info("\n📌 测试9: 图像数据移除")
    
    log_manager = LoggerManager()
    log_manager.enable_privacy_protection()
    
    # 模拟包含图像数据的日志
    data_with_image = {
        "request_id": "req-123",
        "user": "alice",
        "image_data": b"\\x89PNG\\r\\n\\x1a\\n" * 100,  # 模拟图像二进制数据
        "img_base64": "data:image/png;base64,iVBORw0KGgoAAAANSU...",  # 模拟base64图像
        "metadata": {
            "size": "1024x768",
            "format": "PNG"
        }
    }
    
    logger.info("原始数据包含:")
    logger.info(f"  • image_data: {len(data_with_image['image_data'])} bytes")
    logger.info(f"  • img_base64: {data_with_image['img_base64'][:30]}...")
    
    protected = log_manager.protect_log_data(data_with_image)
    
    logger.info("\n保护后数据:")
    for key, value in protected.items():
        if isinstance(value, dict) and 'removed' in value:
            logger.info(f"  • {key}: [已移除 - {value}]")
        else:
            logger.info(f"  • {key}: {value}")


def main():
    """主测试函数"""
    logger.info("=" * 60)
    logger.info("🔒 开始隐私保护测试")
    logger.info("=" * 60)
    
    try:
        # 运行所有测试
        test_sensitive_data_detection()
        test_data_masking()
        test_text_masking()
        test_dict_masking()
        test_access_control()
        test_logger_with_privacy()
        test_privacy_configuration()
        test_audit_log()
        test_image_data_removal()
        
        logger.info("\n" + "=" * 60)
        logger.success("✅ 隐私保护测试完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()