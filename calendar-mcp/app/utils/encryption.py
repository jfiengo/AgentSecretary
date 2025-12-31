"""Fernet encryption utilities for OAuth tokens."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings


def get_fernet() -> Fernet:
    """Get Fernet instance using SECRET_KEY."""
    settings = get_settings()
    # Derive a valid Fernet key from the secret key
    # Fernet requires a 32-byte base64-encoded key
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_token(token: str) -> str:
    """Encrypt a token string."""
    fernet = get_fernet()
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token string."""
    fernet = get_fernet()
    decrypted = fernet.decrypt(encrypted_token.encode())
    return decrypted.decode()

