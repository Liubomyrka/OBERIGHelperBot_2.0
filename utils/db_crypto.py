import base64
import hashlib
import os


_ENC_PREFIX = "encv1:"


def _derive_key_material(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _keystream(key_material: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key_material + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_text(plain: str, secret: str | None) -> str:
    if not secret or not plain:
        return plain
    if plain.startswith(_ENC_PREFIX):
        return plain
    data = plain.encode("utf-8")
    nonce = os.urandom(16)
    key_material = _derive_key_material(secret)
    stream = _keystream(key_material, nonce, len(data))
    cipher = bytes(a ^ b for a, b in zip(data, stream))
    payload = base64.urlsafe_b64encode(nonce + cipher).decode("ascii")
    return f"{_ENC_PREFIX}{payload}"


def decrypt_text(value: str, secret: str | None) -> str:
    if not value or not isinstance(value, str):
        return value
    if not value.startswith(_ENC_PREFIX):
        return value
    if not secret:
        return value
    payload = value[len(_ENC_PREFIX) :]
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, cipher = raw[:16], raw[16:]
        key_material = _derive_key_material(secret)
        stream = _keystream(key_material, nonce, len(cipher))
        plain = bytes(a ^ b for a, b in zip(cipher, stream))
        return plain.decode("utf-8")
    except Exception:
        return value


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)

