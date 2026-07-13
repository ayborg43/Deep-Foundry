"""
Envelope encryption for secrets at rest — provider API keys and MFA secrets —
per SECURITY.md §6. MVP: a single Fernet key from `settings.FIELD_ENCRYPTION_KEY`;
a dedicated secrets manager is the documented V2+ upgrade path, not built here.
"""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"` and set it in the environment.'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_to_bytes(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_from_bytes(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt value — wrong key or corrupted data.") from exc


def encrypt_to_text(plaintext: str) -> str:
    return encrypt_to_bytes(plaintext).decode()


def decrypt_from_text(ciphertext: str) -> str:
    return decrypt_from_bytes(ciphertext.encode())


def mask_secret(plaintext: str, visible: int = 4) -> str:
    """`sk-abc123...` -> `sk-a...f123` style masking for display, never the real value."""
    if len(plaintext) <= visible * 2:
        return "*" * len(plaintext)
    return f"{plaintext[:visible]}...{plaintext[-visible:]}"
