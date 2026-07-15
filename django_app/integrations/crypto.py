import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet_key_from_source(source: str) -> bytes:
    """Generate Fernet key from a key source string."""
    return base64.urlsafe_b64encode(hashlib.sha256(source.encode()).digest())


def _get_encryption_keys() -> list[bytes]:
    """Get list of encryption keys in priority order (current first, old keys second)."""
    keys = []
    current_source = settings.FIELD_ENCRYPTION_KEY or settings.SECRET_KEY
    keys.append(_fernet_key_from_source(current_source))

    old_keys = getattr(settings, 'FIELD_ENCRYPTION_KEY_ROTATION', [])
    for old_source in old_keys:
        if old_source != current_source:
            keys.append(_fernet_key_from_source(old_source))

    return keys


def encrypt(value: str) -> str:
    """Encrypt value with current key."""
    if not value:
        return ""
    keys = _get_encryption_keys()
    fernet = Fernet(keys[0])
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt value, trying current key first, then old keys. Raises InvalidToken if all fail."""
    if not value:
        return ""
    keys = _get_encryption_keys()
    last_error = None

    for key in keys:
        try:
            fernet = Fernet(key)
            return fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            last_error = error
            continue

    raise last_error or InvalidToken("No valid keys for decryption")
