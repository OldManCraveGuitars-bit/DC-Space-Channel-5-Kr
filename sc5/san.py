"""CRI SAN YU0M frames: raster 16x16 blocks, U/V and four 8x8 Y tiles."""
import struct
import numpy as np
from PIL import Image


def san_info(data):
    if len(data) < 64 or data[:4] != b"SAN " or data[8:12] != b"YU0M":
        raise ValueError("Unsupported SAN format")
    header, count, width, height, frame_bytes = (
        struct.unpack_from("<I", data, p)[0] for p in (4, 12, 16, 20, 24))
    size = struct.unpack_from("<I", data, 60)[0]
    if (header != 56 or data[56:60] != b"DATA" or not width or not height
            or width % 16 or height % 16 or frame_bytes != width * height * 3 // 2
            or size != count * frame_bytes or len(data) != 64 + size):
        raise ValueError("Invalid SAN dimensions or payload size")
    return {"frame_count": count, "width": width, "height": height,
            "frame_bytes": frame_bytes, "pixel_format": "YU0M"}


def decode_san_frame(data, index=0):
    info = san_info(data)
    if not 0 <= index < info["frame_count"]:
        raise IndexError(index)
    w, h = info["width"], info["height"]
    start = 64 + index * info["frame_bytes"]
    blocks = np.frombuffer(data, dtype=np.uint8, count=info["frame_bytes"],
                           offset=start).reshape(h // 16, w // 16, 384)
    u = blocks[:, :, :64].reshape(h // 16, w // 16, 8, 8).transpose(0, 2, 1, 3).reshape(h // 2, w // 2)
    v = blocks[:, :, 64:128].reshape(h // 16, w // 16, 8, 8).transpose(0, 2, 1, 3).reshape(h // 2, w // 2)
    ytiles = np.empty((h // 16, w // 16, 16, 16), dtype=np.uint8)
    for q in range(4):
        ytiles[:, :, (q // 2) * 8:(q // 2 + 1) * 8,
               (q % 2) * 8:(q % 2 + 1) * 8] = blocks[:, :, 128 + q * 64:192 + q * 64].reshape(h // 16, w // 16, 8, 8)
    y = ytiles.transpose(0, 2, 1, 3).reshape(h, w).astype(np.float32)
    u = u.repeat(2, 0).repeat(2, 1).astype(np.float32) - 128
    v = v.repeat(2, 0).repeat(2, 1).astype(np.float32) - 128
    rgb = np.stack((y + 1.402 * v, y - .344136 * u - .714136 * v,
                    y + 1.772 * u), axis=-1)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def encode_san_regions(data, index, image, regions):
    """Replace only approved 2x2 chroma cells; retain other SAN bytes exactly."""
    info = san_info(data)
    if not 0 <= index < info["frame_count"]:
        raise IndexError(index)
    before = np.asarray(decode_san_frame(data, index))
    after = np.asarray(image.convert("RGB"))
    if before.shape != after.shape:
        raise ValueError("SAN frame dimensions differ")
    h, w = before.shape[:2]
    allowed = np.zeros((h, w), dtype=bool)
    for x, y, width, height in regions:
        if any(v % 2 for v in (x, y, width, height)):
            raise ValueError("SAN regions must follow the 2x2 chroma grid")
        if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > w or y + height > h:
            raise ValueError("SAN edit region is outside the frame")
        allowed[y:y + height, x:x + width] = True
    changed = np.any(before != after, axis=2)
    if np.any(changed & ~allowed):
        raise ValueError("SAN pixels changed outside approved regions")
    cells = changed.reshape(h // 2, 2, w // 2, 2).any(axis=(1, 3))
    packed = bytearray(data)
    start = 64 + index * info["frame_bytes"]
    rgb = after.astype(np.float64)
    y = .299 * rgb[:, :, 0] + .587 * rgb[:, :, 1] + .114 * rgb[:, :, 2]
    u = (rgb[:, :, 2] - y) / 1.772 + 128
    v = (rgb[:, :, 0] - y) / 1.402 + 128
    for cy, cx in zip(*np.where(cells)):
        py, px = int(cy) * 2, int(cx) * 2
        block = start + ((py // 16) * (w // 16) + px // 16) * 384
        chroma = (py % 16 // 2) * 8 + px % 16 // 2
        packed[block + chroma] = int(np.clip(np.rint(u[py:py + 2, px:px + 2].mean()), 0, 255))
        packed[block + 64 + chroma] = int(np.clip(np.rint(v[py:py + 2, px:px + 2].mean()), 0, 255))
        for dy in range(2):
            for dx in range(2):
                row, col = py + dy, px + dx
                if not changed[row, col]:
                    continue
                local_y, local_x = row % 16, col % 16
                tile = local_y // 8 * 2 + local_x // 8
                offset = block + 128 + tile * 64 + local_y % 8 * 8 + local_x % 8
                packed[offset] = int(np.clip(np.rint(y[row, col]), 0, 255))
    packed = bytes(packed)
    decoded = np.asarray(decode_san_frame(packed, index))
    if np.any(decoded[~allowed] != before[~allowed]):
        raise ValueError("SAN encoding changed pixels outside approved regions")
    error = decoded.astype(float) - after.astype(float)
    return packed, {"frame": index, "regions": regions, "changed_chroma_cells": int(cells.sum()),
                    "changed_pixels": int(changed.sum()), "outside_regions_exact": True,
                    "rmse": float(np.sqrt(np.mean(error[allowed] ** 2))) if allowed.any() else 0.0}
