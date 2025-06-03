from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

__all__ = ["embed", "extract"]

_HEADER_BITS = 32 
_MAGIC = b"HAMM"
_MAGIC_BITS = np.unpackbits(np.frombuffer(_MAGIC, dtype=np.uint8))

H = np.array([[((j + 1) >> r) & 1 for j in range(15)] for r in range(4)], dtype=np.uint8)  # shape (4,15)


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
    if len(bits) % 8 != 0:
        raise ValueError("Bit array length must be multiple of 8")
    return np.packbits(bits).tobytes()


def embed(image_path: str, payload: bytes, rate: float, out_path: str) -> None:
    if not (0.0 <= rate <= 1.0):
        raise ValueError("Rate must be between 0 and 1")

    img, arr = _open_rgb_bmp(image_path)
    flat = arr.reshape(-1)

    total_blocks = len(flat) // 15
    usable_blocks = int(total_blocks * rate)
    capacity_bits = usable_blocks * 4

    stream = _MAGIC + len(payload).to_bytes(4, "little") + payload
    bits = _bits_from_bytes(stream)
    needed_bits = len(bits)

    if needed_bits > capacity_bits:
        raise ValueError(f"Need {needed_bits} bits but capacity at chosen rate is {capacity_bits} bits")

    if needed_bits % 4:
        pad = 4 - (needed_bits % 4)
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    nibbles = bits.reshape(-1, 4)

    stego_flat = flat.copy()

    for block_idx, m in enumerate(nibbles):
        if block_idx >= usable_blocks:
            break 
        start = block_idx * 15
        cover_bits = stego_flat[start:start + 15] & 1 
        syndrome = (H @ cover_bits) & 1
        diff = syndrome ^ m
        diff_val = diff[0] | (diff[1] << 1) | (diff[2] << 2) | (diff[3] << 3)
        if diff_val != 0:
            pos = diff_val - 1 
            stego_flat[start + pos] ^= 1

    stego_arr = stego_flat.reshape(arr.shape)
    Image.fromarray(stego_arr, "RGB").save(out_path, format="BMP")


def extract(image_path: str, rate: float = 1.0) -> bytes:
    if not (0.0 < rate <= 1.0):
        raise ValueError("Rate must be between 0 and 1")

    img, arr = _open_rgb_bmp(image_path)
    flat = arr.reshape(-1)
    total_blocks = len(flat) // 15
    usable_blocks = int(total_blocks * rate)

    bits_out = []
    for block_idx in range(usable_blocks):
        start = block_idx * 15
        cover_bits = flat[start:start + 15] & 1
        syndrome = (H @ cover_bits) & 1
        bits_out.extend(syndrome.tolist())

    bits = np.array(bits_out, dtype=np.uint8)

    magic_len = len(_MAGIC_BITS)
    if len(bits) < magic_len + _HEADER_BITS:
        raise ValueError("Rate too low or image too small to contain magic and header")

    magic_bits = bits[:magic_len]
    if not np.array_equal(magic_bits, _MAGIC_BITS):
        raise ValueError("Magic header mismatch: likely not a HAMM stego image")

    length_bits = bits[magic_len:magic_len + _HEADER_BITS]
    payload_len = int.from_bytes(_bytes_from_bits(length_bits), "little")

    total_bits_needed = magic_len + _HEADER_BITS + payload_len * 8
    if total_bits_needed > len(bits):
        raise ValueError("Declared payload length exceeds embedded data")

    payload_bits = bits[magic_len + _HEADER_BITS:total_bits_needed]
    return _bytes_from_bits(payload_bits)
