from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

__all__ = [
    "embed",
    "extract",
]

_LENGTH_HEADER_BITS = 32  # 4 bytes little‑endian length prefix
_MAGIC = b"LSBR"  # 4‑byte identifier
_MAGIC_BITS = np.unpackbits(np.frombuffer(_MAGIC, dtype=np.uint8))


def _open_rgb_bmp(path: str | Path) -> Tuple[Image.Image, np.ndarray]:
    img = Image.open(path)
    if img.format != "BMP":
        raise ValueError("Only BMP images are supported (got {} format)".format(img.format))
    if img.mode != "RGB":
        try:
            img = img.convert("RGB")
        except Exception:
            raise ValueError("Image must be 24‑bit RGB BMP")
    arr = np.array(img, dtype=np.uint8)
    return img, arr


def _bits_from_bytes(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def _bytes_from_bits(bits: np.ndarray) -> bytes:
    if len(bits) % 8 != 0:
        raise ValueError("Bit array length must be multiple of 8")
    return np.packbits(bits).tobytes()


def embed(image_path: str, payload: bytes, rate: float, out_path: str) -> None:
    if not (0.0 <= rate <= 1.0):
        raise ValueError("Rate must be between 0.0 and 1.0")

    # open image
    img, arr = _open_rgb_bmp(image_path)
    flat = arr.reshape(-1)  

    capacity_bits = len(flat)  
    max_payload_bits = int(capacity_bits * rate)

    payload_len = len(payload)
    if payload_len >= 2 ** 32:
        raise ValueError("Payload too large (>= 4 GiB)")

    header = payload_len.to_bytes(4, byteorder="little")
    full = _MAGIC + header + payload
    full_bits = _bits_from_bytes(full)

    if len(full_bits) > max_payload_bits:
        raise ValueError(
            f"Payload + header + magic ({len(full_bits)} bits) exceeds capacity at chosen rate "
            f"({max_payload_bits} bits)"
        )

    stego_flat = flat.copy()
    stego_flat[: len(full_bits)] &= 0xFE  # clear LSB
    stego_flat[: len(full_bits)] |= full_bits

    stego_arr = stego_flat.reshape(arr.shape)
    stego_img = Image.fromarray(stego_arr, mode="RGB")
    stego_img.save(out_path, format="BMP")


def extract(image_path: str, rate: float = 1.0) -> bytes:
    if not (0.0 < rate <= 1.0):
        raise ValueError("Rate must be between 0.0 and 1.0")

    img, arr = _open_rgb_bmp(image_path)
    flat = arr.reshape(-1)
    max_bits = int(len(flat) * rate)

    needed_magic_bits = len(_MAGIC_BITS)
    if max_bits < needed_magic_bits + _LENGTH_HEADER_BITS:
        raise ValueError("Rate too low — magic + header doesn't fit")

    magic_bits = flat[:needed_magic_bits] & 1
    if not np.array_equal(magic_bits, _MAGIC_BITS):
        raise ValueError("Magic header mismatch: likely not an LSBR stego image")

    header_start = needed_magic_bits
    header_bits = flat[header_start:header_start + _LENGTH_HEADER_BITS] & 1
    payload_len = int.from_bytes(_bytes_from_bits(header_bits), byteorder="little")

    total_bits_needed = needed_magic_bits + _LENGTH_HEADER_BITS + payload_len * 8
    if total_bits_needed > max_bits:
        raise ValueError("Declared payload length exceeds available capacity at given rate")

    payload_bits = flat[header_start + _LENGTH_HEADER_BITS:total_bits_needed] & 1
    return _bytes_from_bits(payload_bits)