from __future__ import annotations

from pathlib import Path
from typing import Tuple
import numpy as np
from PIL import Image

__all__ = ["embed", "extract"]

_LENGTH_HEADER_BITS = 32 
_MAGIC = b"LSBM"
_MAGIC_BITS = np.unpackbits(np.frombuffer(_MAGIC, dtype=np.uint8))
_rng = np.random.default_rng()


def _open_rgb_bmp(path: str | Path) -> Tuple[Image.Image, np.ndarray]:
    img = Image.open(path)
    if img.format != "BMP":
        raise ValueError(f"Only BMP images are supported (got {img.format})")
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
    if len(bits) % 8:
        raise ValueError("Bit array length must be multiple of 8")
    return np.packbits(bits).tobytes()


def embed(image_path: str, payload: bytes, rate: float, out_path: str) -> None:
    if not (0.0 <= rate <= 1.0):
        raise ValueError("Rate must be between 0.0 and 1.0")

    img, arr = _open_rgb_bmp(image_path)
    flat = arr.reshape(-1)  # view [B,G,R,B,G,R,…]

    capacity_bits = int(len(flat) * rate)

    payload_len = len(payload)
    if payload_len >= 2 ** 32:
        raise ValueError("Payload too large (>=4 GiB)")

    header = payload_len.to_bytes(4, "little")
    stream = _MAGIC + header + payload
    bits = _bits_from_bytes(stream)

    if len(bits) > capacity_bits:
        raise ValueError(
            f"Need {len(bits)} bits, but capacity at chosen rate is {capacity_bits} bits"
        )

    stego_flat = flat.copy()
    embed_zone = stego_flat[: len(bits)]

    current_lsb = embed_zone & 1
    mismatch_mask = current_lsb != bits

    indices = np.nonzero(mismatch_mask)[0]
    if indices.size:
        plus_mask = _rng.integers(0, 2, size=indices.size, dtype=np.uint8)  # 0/1
        deltas = np.where(plus_mask == 1, 1, -1).astype(np.int16)

        vals = embed_zone[indices].astype(np.int16)
        deltas[(vals == 0) & (deltas == -1)] = 1
        deltas[(vals == 255) & (deltas == 1)] = -1

        embed_zone[indices] = (vals + deltas) & 0xFF

    stego_arr = stego_flat.reshape(arr.shape)
    Image.fromarray(stego_arr, "RGB").save(out_path, format="BMP")


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
        raise ValueError("Magic header mismatch: likely not an LSBM stego image")

    header_start = needed_magic_bits
    header_bits = flat[header_start:header_start + _LENGTH_HEADER_BITS] & 1
    payload_len = int.from_bytes(_bytes_from_bits(header_bits), "little")

    total_bits = needed_magic_bits + _LENGTH_HEADER_BITS + payload_len * 8
    if total_bits > max_bits:
        raise ValueError("Declared payload length exceeds available capacity at given rate")

    payload_bits = flat[header_start + _LENGTH_HEADER_BITS:total_bits] & 1
    return _bytes_from_bits(payload_bits)
