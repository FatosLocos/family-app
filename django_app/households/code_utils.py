import hashlib
import hmac
import secrets


def generate_invite_code() -> str:
    """Generate a cryptographically secure invite code."""
    return secrets.token_urlsafe(18)


def hash_invite_code(code: str) -> str:
    """Hash an invite code using PBKDF2 with SHA-256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        b"family-app-invite",  # Fixed salt for deterministic hashing
        100000,  # 100k iterations
    ).hex()


def verify_invite_code(code: str, code_hash: str) -> bool:
    """Verify an invite code against its hash."""
    return hmac.compare_digest(hash_invite_code(code), code_hash)
