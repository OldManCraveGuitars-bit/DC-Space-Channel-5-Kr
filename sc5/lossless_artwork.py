"""Store the tiny disc-selection wordmark without VQ glyph distortion.

The original file has only seven spare VQ entries. A standard twiddled 16-bit
PVR fits in the unused, zero-filled end of track 5. Other file extents stay put;
only this file's root directory record is updated in a copied track 3.
"""
from pathlib import Path
import hashlib
import shutil
import struct

import numpy as np

from .assets import decode_pvr
from .disc import PAYLOAD, SECTOR
from .sector import update_mode1, verify_mode1


def encode_lossless_artwork(original, image, regions):
    pos = original.find(b"PVRT")
    if pos < 0:
        raise ValueError("Missing PVR header")
    pf = original[pos + 8]
    width, height = struct.unpack_from("<HH", original, pos + 12)
    if pf != 2 or width != 256 or height != 256 or image.size != (width, height):
        raise ValueError("Lossless disc artwork requires original 256x256 ARGB4444")
    before = np.asarray(decode_pvr(original))
    after = np.asarray(image.convert("RGBA"), dtype=np.uint32)
    allowed = np.zeros((height, width), dtype=bool)
    for x, y, w, h in regions:
        if min(x, y, w, h) < 0 or x + w > width or y + h > height:
            raise ValueError("Invalid artwork edit rectangle")
        allowed[y:y + h, x:x + w] = True
    if np.any(before[~allowed] != after[~allowed]):
        raise ValueError("Pixels outside the wordmark changed")
    r, g, b, a = (after[:, :, channel] for channel in range(4))
    pixels = (((a * 15 + 127) // 255) << 12) | (((r * 15 + 127) // 255) << 8)
    pixels |= (((g * 15 + 127) // 255) << 4) | ((b * 15 + 127) // 255)
    yy, xx = np.indices((height, width))
    morton = np.zeros((height, width), dtype=np.int32)
    for bit in range(8):
        morton |= ((yy >> bit) & 1) << (bit * 2)
        morton |= ((xx >> bit) & 1) << (bit * 2 + 1)
    ordered = np.empty(width * height, dtype="<u2")
    ordered[morton.ravel()] = pixels.ravel()
    header = bytearray(original[:pos + 16])
    header[pos + 9] = 1  # Standard non-mipmapped twiddled 16-bit texture.
    struct.pack_into("<I", header, pos + 4, 8 + ordered.nbytes)
    result = bytes(header) + ordered.tobytes()
    if not np.array_equal(np.asarray(decode_pvr(result)), after):
        raise ValueError("Artwork colors must be exactly representable in ARGB4444")
    return result, {"packing_mode": "lossless_twiddled", "outside_regions_exact": True,
                    "full_pixel_roundtrip_exact": True, "premultiplied_rmse": 0.0,
                    "length_unchanged": False, "original_size": len(original),
                    "new_size": len(result)}


def relocate_artwork(image, replacement, output_track5, output_track3):
    """Relocate only 0GDTEX in generated copies, after checking the free tail."""
    output_track5, output_track3 = Path(output_track5), Path(output_track3)
    if output_track5.resolve() == image.track5.resolve() or output_track3.resolve() == image.track3.resolve():
        raise ValueError("Refusing to alter original tracks")
    entries = image.entries()
    entry = next(e for e in entries if e.name == "0GDTEX.PVR")
    raw = Path(replacement).read_bytes()
    decoded = decode_pvr(raw)
    if decoded.size != (256, 256) or raw[raw.find(b"PVRT") + 9] != 1:
        raise ValueError("Unexpected lossless disc artwork format")
    new_lba = max(e.lba + (e.size + PAYLOAD - 1) // PAYLOAD for e in entries)
    sectors = (len(raw) + PAYLOAD - 1) // PAYLOAD
    if new_lba < image.track5_start or new_lba + sectors > image.track5_start + image.track5_sectors:
        raise ValueError("No unused track 5 tail for lossless disc artwork")
    if any(image.read(new_lba, sectors * PAYLOAD)):
        raise ValueError("Original unused track tail is not empty")
    directory = bytearray(image.read(image.root_lba, image.root_size))
    offset, matched = 0, []
    while offset < len(directory):
        length = directory[offset]
        if not length:
            offset = (offset // PAYLOAD + 1) * PAYLOAD
            continue
        if length < 34 or offset + length > len(directory):
            raise ValueError("Broken root directory record")
        name_len = directory[offset + 32]
        name = bytes(directory[offset + 33:offset + 33 + name_len]).split(b";")[0]
        if name == b"0GDTEX.PVR":
            if int.from_bytes(directory[offset + 2:offset + 6], "little") != entry.lba:
                raise ValueError("Root artwork extent mismatch")
            matched.append(offset)
        offset += length
    if len(matched) != 1:
        raise ValueError("Expected one artwork directory entry")
    offset = matched[0]
    if offset // PAYLOAD != (offset + directory[offset] - 1) // PAYLOAD:
        raise ValueError("Directory record crosses a sector")
    struct.pack_into("<I", directory, offset + 2, new_lba)
    struct.pack_into(">I", directory, offset + 6, new_lba)
    struct.pack_into("<I", directory, offset + 10, len(raw))
    struct.pack_into(">I", directory, offset + 14, len(raw))
    directory_sector = image.root_lba + offset // PAYLOAD
    if not image.volume_start <= directory_sector < image.volume_start + image.track3_sectors:
        raise ValueError("Expected artwork directory on track 3")
    with output_track5.open("r+b") as stream:
        for n in range(sectors):
            stream.seek((new_lba + n - image.track5_start) * SECTOR)
            old = stream.read(SECTOR)
            if not verify_mode1(old) or any(old[16:16 + PAYLOAD]):
                raise ValueError("Generated artwork destination is not an empty valid sector")
            payload = raw[n * PAYLOAD:(n + 1) * PAYLOAD].ljust(PAYLOAD, b"\0")
            updated = update_mode1(old, payload)
            if not verify_mode1(updated):
                raise AssertionError("Invalid generated artwork sector")
            stream.seek((new_lba + n - image.track5_start) * SECTOR)
            stream.write(updated)
    output_track3.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image.track3, output_track3)
    index = directory_sector - image.volume_start
    payload_start = offset // PAYLOAD * PAYLOAD
    with output_track3.open("r+b") as stream:
        stream.seek(index * SECTOR)
        old = stream.read(SECTOR)
        if not verify_mode1(old):
            raise ValueError("Invalid original directory sector")
        updated = update_mode1(old, directory[payload_start:payload_start + PAYLOAD])
        if not verify_mode1(updated):
            raise AssertionError("Invalid generated directory sector")
        stream.seek(index * SECTOR)
        stream.write(updated)
    return {"name": entry.name, "old_lba": entry.lba, "new_lba": new_lba,
            "old_size": entry.size, "new_size": len(raw), "track5_sectors": sectors,
            "track3_directory_lba": directory_sector, "track3_sectors": 1,
            "other_file_extents_unchanged": True, "original_tail_zero_verified": True,
            "pvr_sha256": hashlib.sha256(raw).hexdigest()}
