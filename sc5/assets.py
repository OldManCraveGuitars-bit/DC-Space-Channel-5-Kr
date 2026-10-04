"""Catalog AFS voices, MPEG clips and Dreamcast PVR textures."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import struct

from .disc import GDImage, FileEntry


def afs_members(data: bytes, archive: str) -> list[dict]:
    if data[:4] != b"AFS\0":
        raise ValueError(f"Not an AFS archive: {archive}")
    count = struct.unpack_from("<I", data, 4)[0]
    if count > 100000 or 8 + count * 8 > len(data):
        raise ValueError("Invalid AFS table")
    members = []
    for i in range(count):
        offset, size = struct.unpack_from("<II", data, 8 + i * 8)
        if offset + size > len(data):
            raise ValueError(f"AFS entry {i} exceeds archive")
        magic = data[offset:offset + 4]
        kind = "ADX" if magic[:2] == b"\x80\x00" else magic.decode("ascii", "replace")
        members.append({"id": f"{archive}:{i:03d}", "archive": archive,
                        "index": i, "offset": offset, "size": size, "kind": kind})
    return members


def media_catalog(image: GDImage, output: Path):
    entries = image.entries()
    audio = []
    animations = []
    for entry in entries:
        if entry.suffix != ".AFS":
            continue
        blob = image.read(entry.lba, entry.size)
        for member in afs_members(blob, entry.name):
            raw = blob[member["offset"]:member["offset"] + member["size"]]
            if member["kind"] == "ADX":
                sample_rate = int.from_bytes(raw[8:12], "big")
                sample_count = int.from_bytes(raw[12:16], "big")
                if not sample_rate or not sample_count:
                    raise ValueError(f"Invalid ADX sample header: {member['id']}")
                audio.append(member | {"channels": raw[7], "sample_rate": sample_rate,
                    "sample_count": sample_count, "duration": sample_count / sample_rate})
            elif member["kind"] == "SAN ":
                from .san import san_info
                animations.append(member | san_info(raw) | {"status": "unreviewed"})
    videos = [{"id": e.name, "name": e.name, "size": e.size,
               "kind": e.suffix[1:], "route": e.name.split("_")[0]}
              for e in entries if e.suffix in (".M1V", ".SFD")]
    catalog = {"audio": audio, "videos": videos, "animations": animations,
               "branch_note": "Catalog contains all named clips and voices; no auto-play path filtering."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    (output.parent / "animations.json").write_text(json.dumps(animations, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog


def pvm_members(data: bytes, archive: str) -> list[dict]:
    if data[:4] != b"PVMH":
        raise ValueError(f"Not a PVM archive: {archive}")
    count = struct.unpack_from("<H", data, 10)[0]
    # This PVMH directory uses 38-byte records: 2-byte index, 28-byte name,
    # 8-byte texture metadata.
    names = []
    for i in range(count):
        record = data[12 + i * 38:12 + (i + 1) * 38]
        if len(record) < 38:
            break
        names.append(record[2:30].split(b"\0")[0].decode("ascii", "replace"))
    chunks = []
    pos = 8 + struct.unpack_from("<I", data, 4)[0]
    for i in range(count):
        if data[pos:pos + 4] == b"GBIX":
            pos += 8 + struct.unpack_from("<I", data, pos + 4)[0]
        if data[pos:pos + 4] != b"PVRT":
            # Some PVMs pad or place secondary metadata between images.
            next_pos = data.find(b"PVRT", pos)
            if next_pos < 0:
                break
            pos = next_pos
        length = struct.unpack_from("<I", data, pos + 4)[0]
        end = pos + 8 + length
        if end > len(data):
            break
        chunks.append({"id": f"{archive}:{i:03d}", "archive": archive,
                       "index": i, "name": names[i] if i < len(names) else str(i),
                       "offset": pos, "size": end - pos,
                       "pixel_format": data[pos + 8], "data_format": data[pos + 9],
                       "width": struct.unpack_from("<H", data, pos + 12)[0],
                       "height": struct.unpack_from("<H", data, pos + 14)[0]})
        pos = end
    return chunks


def image_catalog(image: GDImage, output: Path):
    images = []
    for e in image.entries():
        if e.suffix == ".PVR":
            data = image.read(e.lba, min(e.size, 64))
            p = data.find(b"PVRT")
            images.append({"id": e.name, "archive": None, "name": e.name,
                           "pixel_format": data[p + 8] if p >= 0 else None,
                           "data_format": data[p + 9] if p >= 0 else None,
                           "width": struct.unpack_from("<H", data, p + 12)[0] if p >= 0 else None,
                           "height": struct.unpack_from("<H", data, p + 14)[0] if p >= 0 else None,
                           "size": e.size})
        elif e.suffix == ".PVM":
            images.extend(pvm_members(image.read(e.lba, e.size), e.name))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(images, ensure_ascii=False, indent=2), encoding="utf-8")
    return images


def _morton(x: int, y: int) -> int:
    out = 0
    bit = 0
    while (1 << bit) <= max(x, y):
        out |= ((y >> bit) & 1) << (2 * bit)
        out |= ((x >> bit) & 1) << (2 * bit + 1)
        bit += 1
    return out


def _color(value: int, pixel_format: int) -> tuple[int, int, int, int]:
    if pixel_format == 0:  # ARGB1555
        return (((value >> 10) & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31,
                (value & 31) * 255 // 31, 255 if value & 0x8000 else 0)
    if pixel_format == 1:  # RGB565
        return (((value >> 11) & 31) * 255 // 31, ((value >> 5) & 63) * 255 // 63,
                (value & 31) * 255 // 31, 255)
    if pixel_format == 2:  # ARGB4444
        return (((value >> 8) & 15) * 17, ((value >> 4) & 15) * 17,
                (value & 15) * 17, ((value >> 12) & 15) * 17)
    raise ValueError(f"Unsupported PVR pixel format {pixel_format}")


def decode_pvr(chunk: bytes):
    """Decode common VQ and 16-bit twiddled PVR to a Pillow RGBA image."""
    from PIL import Image
    p = chunk.find(b"PVRT")
    if p < 0:
        raise ValueError("PVRT header missing")
    pixel_format, data_format = chunk[p + 8], chunk[p + 9]
    width, height = struct.unpack_from("<HH", chunk, p + 12)
    if not width or not height or width > 2048 or height > 2048:
        raise ValueError("Invalid texture dimensions")
    pixels = chunk[p + 16:p + 8 + struct.unpack_from("<I", chunk, p + 4)[0]]
    img = Image.new("RGBA", (width, height))
    put = img.putpixel
    if data_format in (3, 4, 16, 17):  # VQ (possibly mipmapped/small codebook)
        count = width * height // 4
        codebook_size = 2048 if data_format in (3, 4) else min(2048, max(128, len(pixels) - count))
        codebook_size -= codebook_size % 8
        if len(pixels) < codebook_size + count:
            raise ValueError("Short VQ payload")
        colors = [_color(struct.unpack_from("<H", pixels, i * 2)[0], pixel_format)
                  for i in range(codebook_size // 2)]
        index_start = codebook_size if data_format in (3, 16) else len(pixels) - count
        bw, bh = width // 2, height // 2
        for by in range(bh):
            for bx in range(bw):
                index = pixels[index_start + _morton(bx, by)] * 4
                if index + 3 >= len(colors):
                    raise ValueError("VQ codebook index out of range")
                # Dreamcast VQ codebook order follows the 2x2 twiddled tile.
                put((bx * 2, by * 2), colors[index])
                put((bx * 2, by * 2 + 1), colors[index + 1])
                put((bx * 2 + 1, by * 2), colors[index + 2])
                put((bx * 2 + 1, by * 2 + 1), colors[index + 3])
    elif data_format in (1, 2):  # 16-bit twiddled, possibly mipmapped
        if len(pixels) < width * height * 2:
            raise ValueError("Short twiddled payload")
        pixel_start = 0 if data_format == 1 else len(pixels) - width * height * 2
        for y in range(height):
            for x in range(width):
                value = struct.unpack_from("<H", pixels, pixel_start + _morton(x, y) * 2)[0]
                put((x, y), _color(value, pixel_format))
    else:
        raise ValueError(f"Unsupported PVR data format {data_format}")
    return img


def encode_vq_like(original: bytes, image) -> bytes:
    """Replace a non-mipmapped VQ PVR image, preserving its header and length.

    Exact when the edited image needs no more than 256 distinct 2x2 blocks.
    This is suitable for white-on-transparent CPRO text pages.
    """
    p = original.find(b"PVRT")
    if p < 0 or original[p + 9] != 3:
        raise ValueError("Original must be a non-mipmapped VQ PVR")
    pixel_format = original[p + 8]
    width, height = struct.unpack_from("<HH", original, p + 12)
    if image.size != (width, height):
        raise ValueError("Replacement dimensions differ from the original")
    if pixel_format not in (0, 1, 2):
        raise ValueError("Unsupported PVR pixel format")
    rgba = image.convert("RGBA")

    def packed(x, y):
        r, g, b, a = rgba.getpixel((x, y))
        if pixel_format == 2:
            return ((a * 15 // 255) << 12) | ((r * 15 // 255) << 8) | ((g * 15 // 255) << 4) | (b * 15 // 255)
        if pixel_format == 1:
            return ((r * 31 // 255) << 11) | ((g * 63 // 255) << 5) | (b * 31 // 255)
        return ((1 if a >= 128 else 0) << 15) | ((r * 31 // 255) << 10) | ((g * 31 // 255) << 5) | (b * 31 // 255)

    codebook = bytearray(2048)
    indices = bytearray(width * height // 4)
    blocks = {}
    for by in range(height // 2):
        for bx in range(width // 2):
            x, y = bx * 2, by * 2
            block = (packed(x, y), packed(x, y + 1), packed(x + 1, y), packed(x + 1, y + 1))
            if block not in blocks:
                if len(blocks) == 256:
                    raise ValueError("Edited image needs more than 256 VQ blocks")
                number = len(blocks)
                blocks[block] = number
                struct.pack_into("<4H", codebook, number * 8, *block)
            indices[_morton(bx, by)] = blocks[block]
    body = codebook + indices
    start = p + 16
    end = start + len(body)
    if end > len(original):
        raise ValueError("VQ replacement exceeds original file")
    result = bytearray(original)
    result[start:end] = body
    return bytes(result)


def encode_vq_regions(original: bytes, image, rectangles: list[list[int]]) -> tuple[bytes, dict]:
    """Encode atlas edits while retaining every original block outside the regions.

    A codebook entry still used outside the edits cannot be changed. Available
    entries are fitted to edited blocks; remaining blocks use the closest entry.
    Transparent RGB is ignored and edges are compared in premultiplied RGBA.
    """
    import numpy as np
    p = original.find(b"PVRT")
    if p < 0 or original[p + 9] != 3:
        raise ValueError("Atlas requires non-mipmapped VQ PVR")
    pf = original[p + 8]
    w, h = struct.unpack_from("<HH", original, p + 12)
    if image.size != (w, h) or pf not in (0, 1, 2):
        raise ValueError("Atlas dimensions or pixel format differ")
    mask = np.zeros((h // 2, w // 2), dtype=bool)
    for x, y, rw, rh in rectangles:
        if min(x, y, rw, rh) < 0 or x + rw > w or y + rh > h:
            raise ValueError("Invalid atlas edit rectangle")
        mask[y // 2:(y + rh + 1) // 2, x // 2:(x + rw + 1) // 2] = True
    if not mask.any():
        raise ValueError("No atlas edit regions")
    start = p + 16
    codebook = np.frombuffer(original, dtype="<u2", count=1024, offset=start).reshape(256, 4).copy()
    indices = np.frombuffer(original, dtype=np.uint8, count=w * h // 4, offset=start + 2048).copy()
    ys, xs = np.indices(mask.shape)
    morton = np.zeros(mask.shape, dtype=np.int32)
    for bit in range(max(w, h).bit_length()):
        morton |= ((ys >> bit) & 1) << (bit * 2)
        morton |= ((xs >> bit) & 1) << (bit * 2 + 1)
    occupied = set(indices[morton[~mask]].tolist())
    free = [i for i in range(256) if i not in occupied]
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint32)
    r, g, b, a = (rgba[:, :, i] for i in range(4))
    if pf == 2:
        packed = (((a * 15 + 127) // 255) << 12) | (((r * 15 + 127) // 255) << 8) | (((g * 15 + 127) // 255) << 4) | ((b * 15 + 127) // 255)
    elif pf == 1:
        packed = (((r * 31 + 127) // 255) << 11) | (((g * 63 + 127) // 255) << 5) | ((b * 31 + 127) // 255)
    else:
        packed = ((a >= 128).astype(np.uint32) << 15) | (((r * 31 + 127) // 255) << 10) | (((g * 31 + 127) // 255) << 5) | ((b * 31 + 127) // 255)
    blocks = np.stack((packed[::2, ::2], packed[1::2, ::2], packed[::2, 1::2], packed[1::2, 1::2]), axis=2)[mask].astype("<u2")
    def features(values):
        pixels = np.array([_color(int(v), pf) for v in values.flat], dtype=np.float32).reshape(-1, 4, 4)
        pixels[:, :, :3] *= pixels[:, :, 3:4] / 255
        return pixels.reshape(-1, 16)
    unique, inverse, counts = np.unique(blocks, axis=0, return_inverse=True, return_counts=True)
    wanted = features(unique)
    # Greedily reserve scarce unused entries for the most costly repeated blocks.
    palette = features(codebook)
    def distances(vectors):
        return ((vectors[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    nearest_error = np.full(len(unique), 1e12, dtype=np.float32)
    if occupied:
        fixed_slots = sorted(occupied)
        for first in range(0, len(unique), 512):
            nearest_error[first:first + 512] = distances(wanted[first:first + 512])[:, fixed_slots].min(axis=1)
    for slot in free:
        selected = int(np.argmax(nearest_error * counts))
        if nearest_error[selected] == 0:
            break
        codebook[slot] = unique[selected]
        palette[slot] = wanted[selected]
        delta = ((wanted - palette[slot]) ** 2).sum(axis=1)
        nearest_error = np.minimum(nearest_error, delta)
    selected_indices = np.empty(len(unique), dtype=np.uint8)
    total_error = 0.0
    for first in range(0, len(unique), 512):
        d = distances(wanted[first:first + 512])
        choices = d.argmin(axis=1)
        selected_indices[first:first + len(choices)] = choices
        total_error += float((d[np.arange(len(choices)), choices] * counts[first:first + len(choices)]).sum())
    indices[morton[mask]] = selected_indices[inverse]
    result = bytearray(original)
    result[start:start + 2048] = codebook.tobytes()
    result[start + 2048:start + 2048 + len(indices)] = indices.tobytes()
    report = {"edited_blocks": int(mask.sum()), "available_entries": len(free),
              "unique_edited_blocks": len(unique), "premultiplied_rmse": (total_error / len(blocks) / 16) ** .5,
              "outside_regions_exact": True, "length_unchanged": len(result) == len(original)}
    # Verify the preservation guarantee at the encoded-block level.
    old_indices = np.frombuffer(original, dtype=np.uint8, count=w * h // 4, offset=start + 2048)
    if not np.array_equal(old_indices[morton[~mask]], indices[morton[~mask]]):
        raise AssertionError("Unedited atlas indices changed")
    old_codebook = np.frombuffer(original, dtype="<u2", count=1024, offset=start).reshape(256, 4)
    if occupied and not np.array_equal(old_codebook[list(occupied)], codebook[list(occupied)]):
        raise AssertionError("Unedited atlas colors changed")
    return bytes(result), report
