"""Pack edited SAN frames while preserving AFS member offsets and sizes."""
import hashlib
from pathlib import Path
from PIL import Image

from .san import decode_san_frame, encode_san_regions, san_info
from .editor_project import safe_name
from .assets import afs_members


def validate_archive(original, replacement, name):
    """Allow SAN image payload edits, retaining AFS layout and every header."""
    if not name.upper().startswith("SANDATA_") or not name.upper().endswith(".AFS"):
        raise ValueError("Only SANDATA image archives are supported")
    if len(original) != len(replacement):
        raise ValueError("SAN AFS archive size changed")
    members = afs_members(original, name)
    if afs_members(replacement, name) != members:
        raise ValueError("SAN AFS member layout changed")
    allowed = []
    san_count = 0
    for member in members:
        start, end = member["offset"], member["offset"] + member["size"]
        before, after = original[start:end], replacement[start:end]
        if member["kind"] != "SAN ":
            if before != after:
                raise ValueError("Non-SAN AFS member changed")
            continue
        san_count += 1
        if san_info(before) != san_info(after) or before[:64] != after[:64]:
            raise ValueError("SAN frame header/layout changed")
        if before != after:
            allowed.append((start + 64, end))
    if not san_count:
        raise ValueError("Archive contains no supported SAN images")
    cursor = 0
    for start, end in sorted(allowed):
        if start < cursor or original[cursor:start] != replacement[cursor:start]:
            raise ValueError("SAN AFS directory, padding or header changed")
        cursor = end
    if original[cursor:] != replacement[cursor:]:
        raise ValueError("SAN AFS directory, padding or header changed")
    return {"SAN_members": san_count, "changed_SAN_members": len(allowed)}


def pack_animations(project, disc):
    entries = {e.name: e for e in disc.entries()}
    archives, reports = {}, []
    for key, record in sorted(project.edits("animations").items()):
        if record.get("status") != "edited":
            continue
        if record.get("text_matches_image") is False:
            raise ValueError(f"{key}: 변경한 문구가 그려진 SAN 프레임 PNG를 가져오세요.")
        item = project.item("animations", key)
        replacements = [frame for frame in range(item["frame_count"])
                        if project.replacement("animations", key, frame).is_file()]
        if not replacements:
            raise FileNotFoundError(f"{key}: 수정 SAN 프레임이 없습니다.")
        name = item["archive"]
        if name not in archives:
            entry = entries[name]
            archives[name] = bytearray(disc.read(entry.lba, entry.size))
        offset = item["offset"]
        raw = bytes(archives[name][offset:offset + item["size"]])
        frame_reports = []
        for frame in replacements:
            if record.get("text_matches_frames", {}).get(str(frame)) is False:
                raise ValueError(f"{key} frame {frame}: 수정한 문구와 PNG가 일치하지 않습니다.")
            path = project.replacement("animations", key, frame)
            with Image.open(path) as image:
                regions = record.get("frame_edit_regions", {}).get(str(frame), [[0, 0, item["width"], item["height"]]])
                raw, report = encode_san_regions(raw, frame, image, regions)
            frame_reports.append(report)
            preview = project.root / "work/packed-san" / safe_name(key) / f"frame{frame:03d}.png"
            preview.parent.mkdir(parents=True, exist_ok=True)
            decode_san_frame(raw, frame).save(preview)
        if len(raw) != item["size"]:
            raise ValueError(f"{key}: SAN member size changed")
        archives[name][offset:offset + item["size"]] = raw
        reports.append({"id": key, "archive": name, "frames": frame_reports,
                        "san_sha256": hashlib.sha256(raw).hexdigest(), "same_member_size": True})
    output = project.root / "assets/san-archives"
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, raw in archives.items():
        path = output / name
        path.write_bytes(raw)
        paths[name] = path
    return paths, reports
