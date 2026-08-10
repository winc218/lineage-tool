"""加密工具 - 对称加密敏感配置"""
import os
from cryptography.fernet import Fernet

# 从环境变量获取密钥，测试用默认值
_KEY = os.environ.get("CONFIG_ENCRYPT_KEY", "")


def _get_fernet() -> Fernet:
    key = _KEY
    if not key:
        # 首次启动自动生成并缓存（生产应通过环境变量显式设置）
        key = Fernet.generate_key().decode()
        os.environ["CONFIG_ENCRYPT_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(text: str) -> str:
    """加密明文，返回 base64 密文"""
    if not text:
        return ""
    return _get_fernet().encrypt(text.encode()).decode()


def decrypt(cipher_text: str) -> str:
    """解密"""
    if not cipher_text:
        return ""
    try:
        return _get_fernet().decrypt(cipher_text.encode()).decode()
    except Exception:
        return ""
