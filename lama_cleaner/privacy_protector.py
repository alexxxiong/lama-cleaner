"""
日志隐私保护模块 - 敏感信息脱敏和访问控制
"""
import re
import hashlib
import ipaddress
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
import json
import os
from datetime import datetime
from loguru import logger


class SensitiveDataType(Enum):
    """敏感数据类型"""
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"  # 社会安全号码
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    SECRET = "secret"
    FILE_PATH = "file_path"
    USERNAME = "username"
    URL = "url"
    IMAGE_DATA = "image_data"


@dataclass
class PrivacyConfig:
    """隐私保护配置"""
    enable_masking: bool = True  # 启用脱敏
    mask_emails: bool = True  # 脱敏邮箱
    mask_phones: bool = True  # 脱敏电话
    mask_ips: bool = True  # 脱敏IP地址
    mask_credit_cards: bool = True  # 脱敏信用卡
    mask_passwords: bool = True  # 脱敏密码
    mask_api_keys: bool = True  # 脱敏API密钥
    mask_file_paths: bool = True  # 脱敏文件路径
    preserve_path_structure: bool = True  # 保留路径结构
    hash_usernames: bool = False  # 是否哈希用户名
    remove_image_data: bool = True  # 移除图像数据
    allowed_domains: List[str] = None  # 允许的域名列表
    sensitive_keys: List[str] = None  # 敏感配置键列表
    
    def __post_init__(self):
        if self.allowed_domains is None:
            self.allowed_domains = []
        if self.sensitive_keys is None:
            self.sensitive_keys = [
                'password', 'passwd', 'pwd', 'secret', 'token',
                'api_key', 'apikey', 'access_token', 'auth_token',
                'private_key', 'secret_key', 'encryption_key',
                'database_url', 'connection_string', 'credentials'
            ]


class SensitiveDataDetector:
    """敏感数据检测器"""
    
    # 正则表达式模式
    PATTERNS = {
        SensitiveDataType.EMAIL: re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),
        SensitiveDataType.PHONE: re.compile(
            r'(\+?[1-9]\d{0,2})?[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
        ),
        SensitiveDataType.CREDIT_CARD: re.compile(
            r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
        ),
        SensitiveDataType.SSN: re.compile(
            r'\b\d{3}-\d{2}-\d{4}\b'
        ),
        SensitiveDataType.API_KEY: re.compile(
            r'[a-zA-Z0-9]{32,}'
        ),
        SensitiveDataType.TOKEN: re.compile(
            r'(bearer\s+)?[a-zA-Z0-9\-_]{20,}\.?[a-zA-Z0-9\-_]*\.?[a-zA-Z0-9\-_]*'
        ),
        SensitiveDataType.URL: re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+'
        )
    }
    
    def detect(self, text: str) -> Dict[SensitiveDataType, List[str]]:
        """检测文本中的敏感数据"""
        detected = {}
        
        for data_type, pattern in self.PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                detected[data_type] = matches
                
        # 检测IP地址
        ip_matches = self._detect_ip_addresses(text)
        if ip_matches:
            detected[SensitiveDataType.IP_ADDRESS] = ip_matches
            
        return detected
        
    def _detect_ip_addresses(self, text: str) -> List[str]:
        """检测IP地址"""
        ip_pattern = re.compile(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
            r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        )
        
        matches = []
        for match in ip_pattern.findall(text):
            try:
                ipaddress.ip_address(match)
                matches.append(match)
            except ValueError:
                pass
                
        return matches


class DataMasker:
    """数据脱敏器"""
    
    def __init__(self, config: PrivacyConfig):
        self.config = config
        self.detector = SensitiveDataDetector()
        
    def mask_email(self, email: str) -> str:
        """脱敏邮箱地址"""
        parts = email.split('@')
        if len(parts) != 2:
            return email
            
        username, domain = parts
        if len(username) > 2:
            masked_username = username[0] + '*' * (len(username) - 2) + username[-1]
        else:
            masked_username = '*' * len(username)
            
        # 保留域名的第一个字符
        domain_parts = domain.split('.')
        if domain_parts[0]:
            domain_parts[0] = domain_parts[0][0] + '***'
            
        return f"{masked_username}@{'.'.join(domain_parts)}"
        
    def mask_phone(self, phone: str) -> str:
        """脱敏电话号码"""
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 7:
            return phone[:3] + '*' * (len(phone) - 7) + phone[-4:]
        return '*' * len(phone)
        
    def mask_ip(self, ip: str) -> str:
        """脱敏IP地址"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            if isinstance(ip_obj, ipaddress.IPv4Address):
                parts = ip.split('.')
                return f"{parts[0]}.{parts[1]}.*.* "
            else:  # IPv6
                return ip[:10] + "***"
        except ValueError:
            return ip
            
    def mask_credit_card(self, cc: str) -> str:
        """脱敏信用卡号"""
        digits = re.sub(r'\D', '', cc)
        if len(digits) >= 12:
            return cc[:6] + '*' * (len(cc) - 10) + cc[-4:]
        return '*' * len(cc)
        
    def mask_path(self, path: str) -> str:
        """脱敏文件路径"""
        p = Path(path)
        
        # 保留文件名但脱敏用户目录
        if '/Users/' in path or '/home/' in path or 'C:\\Users\\' in path:
            parts = p.parts
            masked_parts = []
            
            for i, part in enumerate(parts):
                if part in ['Users', 'home'] and i + 1 < len(parts):
                    masked_parts.append(part)
                    masked_parts.append('***')
                    i += 1  # 跳过用户名
                elif i > 0 and parts[i-1] in ['Users', 'home']:
                    continue  # 已经被处理
                else:
                    masked_parts.append(part)
                    
            return str(Path(*masked_parts))
            
        # 只保留文件名和父目录
        if self.config.preserve_path_structure and len(p.parts) > 2:
            return f".../{p.parent.name}/{p.name}"
            
        return f".../{p.name}"
        
    def mask_text(self, text: str) -> str:
        """对文本进行脱敏处理"""
        if not self.config.enable_masking:
            return text
            
        result = text
        
        # 检测敏感数据
        detected = self.detector.detect(text)
        
        # 脱敏邮箱
        if self.config.mask_emails and SensitiveDataType.EMAIL in detected:
            for email in detected[SensitiveDataType.EMAIL]:
                result = result.replace(email, self.mask_email(email))
                
        # 脱敏电话
        if self.config.mask_phones and SensitiveDataType.PHONE in detected:
            for phone in detected[SensitiveDataType.PHONE]:
                if len(phone) > 6:  # 避免误判
                    result = result.replace(phone, self.mask_phone(phone))
                    
        # 脱敏IP地址
        if self.config.mask_ips and SensitiveDataType.IP_ADDRESS in detected:
            for ip in detected[SensitiveDataType.IP_ADDRESS]:
                result = result.replace(ip, self.mask_ip(ip))
                
        # 脱敏信用卡
        if self.config.mask_credit_cards and SensitiveDataType.CREDIT_CARD in detected:
            for cc in detected[SensitiveDataType.CREDIT_CARD]:
                result = result.replace(cc, self.mask_credit_card(cc))
                
        return result
        
    def mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """对字典数据进行脱敏"""
        if not self.config.enable_masking:
            return data
            
        masked = {}
        
        for key, value in data.items():
            # 检查是否为敏感键
            is_sensitive_key = any(
                sensitive in key.lower() 
                for sensitive in self.config.sensitive_keys
            )
            
            if is_sensitive_key:
                # 完全脱敏敏感值
                masked[key] = "***REDACTED***"
            elif isinstance(value, str):
                # 对字符串值进行脱敏
                masked[key] = self.mask_text(value)
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                masked[key] = self.mask_dict(value)
            elif isinstance(value, list):
                # 处理列表
                masked[key] = [
                    self.mask_dict(item) if isinstance(item, dict)
                    else self.mask_text(str(item)) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
                
        return masked


class LogAccessController:
    """日志访问控制器"""
    
    def __init__(self):
        self.permissions = {}
        self.roles = {
            'admin': ['read', 'write', 'delete', 'export'],
            'developer': ['read', 'write', 'export'],
            'viewer': ['read'],
            'auditor': ['read', 'export']
        }
        self.user_roles = {}
        
    def add_user(self, user_id: str, role: str):
        """添加用户和角色"""
        if role in self.roles:
            self.user_roles[user_id] = role
            logger.info(f"用户 {user_id} 被赋予角色: {role}")
        else:
            logger.warning(f"未知角色: {role}")
            
    def check_permission(self, user_id: str, action: str) -> bool:
        """检查用户权限"""
        if user_id not in self.user_roles:
            return False
            
        role = self.user_roles[user_id]
        allowed_actions = self.roles.get(role, [])
        
        return action in allowed_actions
        
    def get_user_role(self, user_id: str) -> Optional[str]:
        """获取用户角色"""
        return self.user_roles.get(user_id)
        
    def revoke_access(self, user_id: str):
        """撤销用户访问权限"""
        if user_id in self.user_roles:
            del self.user_roles[user_id]
            logger.info(f"用户 {user_id} 的访问权限已撤销")


class PrivacyProtector:
    """隐私保护管理器"""
    
    def __init__(self, config: Optional[PrivacyConfig] = None):
        self.config = config or PrivacyConfig()
        self.masker = DataMasker(self.config)
        self.access_controller = LogAccessController()
        self.audit_log = []
        
    def protect_log_message(self, message: str) -> str:
        """保护日志消息中的隐私信息"""
        return self.masker.mask_text(message)
        
    def protect_log_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """保护日志数据中的隐私信息"""
        # 移除图像数据
        if self.config.remove_image_data:
            protected = self._remove_image_data(data.copy())
        else:
            protected = data.copy()
            
        # 脱敏其他数据
        return self.masker.mask_dict(protected)
        
    def _remove_image_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """移除图像数据，只保留元数据"""
        for key in list(data.keys()):
            if any(img_key in key.lower() for img_key in ['image', 'img', 'picture', 'photo']):
                if isinstance(data[key], (bytes, bytearray)):
                    # 替换为元数据
                    data[key] = {
                        'type': 'image',
                        'size': len(data[key]),
                        'removed': True
                    }
                elif isinstance(data[key], str) and len(data[key]) > 1000:
                    # 可能是base64编码的图像
                    if data[key].startswith('data:image'):
                        data[key] = {
                            'type': 'base64_image',
                            'removed': True
                        }
                        
        return data
        
    def check_access(self, user_id: str, action: str, resource: Optional[str] = None) -> bool:
        """检查访问权限"""
        has_permission = self.access_controller.check_permission(user_id, action)
        
        # 记录审计日志
        self.audit_log.append({
            'user_id': user_id,
            'action': action,
            'resource': resource,
            'granted': has_permission,
            'timestamp': datetime.now().isoformat()
        })
        
        return has_permission
        
    def sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """清理配置中的敏感信息"""
        return self.masker.mask_dict(config)
        
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取审计日志"""
        return self.audit_log[-limit:]
        
    def export_privacy_report(self) -> Dict[str, Any]:
        """导出隐私保护报告"""
        return {
            'config': {
                'masking_enabled': self.config.enable_masking,
                'masked_types': [
                    'emails' if self.config.mask_emails else None,
                    'phones' if self.config.mask_phones else None,
                    'ips' if self.config.mask_ips else None,
                    'credit_cards' if self.config.mask_credit_cards else None,
                    'passwords' if self.config.mask_passwords else None,
                    'api_keys' if self.config.mask_api_keys else None,
                    'file_paths' if self.config.mask_file_paths else None,
                ],
                'sensitive_keys': self.config.sensitive_keys
            },
            'access_control': {
                'roles': self.access_controller.roles,
                'users': len(self.access_controller.user_roles)
            },
            'audit_summary': {
                'total_access_checks': len(self.audit_log),
                'granted': sum(1 for log in self.audit_log if log['granted']),
                'denied': sum(1 for log in self.audit_log if not log['granted'])
            }
        }


# 全局隐私保护器实例
privacy_protector = PrivacyProtector()

# 导出便捷函数
def protect_message(message: str) -> str:
    """保护日志消息的便捷函数"""
    return privacy_protector.protect_log_message(message)

def protect_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """保护日志数据的便捷函数"""
    return privacy_protector.protect_log_data(data)

def check_log_access(user_id: str, action: str) -> bool:
    """检查日志访问权限的便捷函数"""
    return privacy_protector.check_access(user_id, action)