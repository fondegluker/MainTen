"""AES-256-GCM + PBKDF2 envelope encryption service for CFMS Configuration and Backups."""

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """Encrypt byte payload using AES-256-GCM + PBKDF2-HMAC-SHA256.
    Returns envelope text bytes in format:
    ENC1
    <base64(salt)>
    <base64(nonce)>
    <base64(ciphertext)>
    """
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")

    salt = os.urandom(16)
    nonce = os.urandom(12)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200000,
    )
    key = kdf.derive(password.encode("utf-8"))

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)

    salt_b64 = base64.b64encode(salt).decode("ascii")
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    cipher_b64 = base64.b64encode(ciphertext).decode("ascii")

    envelope = f"ENC1\n{salt_b64}\n{nonce_b64}\n{cipher_b64}"
    return envelope.encode("utf-8")


def decrypt_bytes(envelope_bytes: bytes, password: str) -> bytes:
    """Decrypt byte payload from ENC1 envelope using AES-256-GCM + PBKDF2-HMAC-SHA256.
    Raises ValueError if password is incorrect, format is invalid, or payload is corrupted.
    """
    if not password:
        raise ValueError("Password is required for encrypted file")

    try:
        text = envelope_bytes.decode("utf-8").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) < 4 or lines[0] != "ENC1":
            raise ValueError("Invalid encryption envelope format")

        salt = base64.b64decode(lines[1])
        nonce = base64.b64decode(lines[2])
        ciphertext = base64.b64decode(lines[3])

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200000,
        )
        key = kdf.derive(password.encode("utf-8"))

        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise ValueError("Decryption failed. Incorrect password or corrupted file.") from e


def is_encrypted_envelope(data: bytes) -> bool:
    """Check if byte payload starts with ENC1 header."""
    try:
        header = data[:10].decode("utf-8", errors="ignore")
        return header.startswith("ENC1")
    except Exception:
        return False
