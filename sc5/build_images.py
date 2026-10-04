"""Pack registered atlas replacements without changing disc archive layouts."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from .assets import decode_pvr, encode_vq_regions
from .editor_project import Project, safe_name
from .lossless_artwork import encode_lossless_artwork
from .common_atlas_storage import encode_common_atlas


def encode_stable_regions(project, original, image, record, all_regions):
    """Retain a previously approved atlas when just one decorative label changes.

    The basis is hash checked and must preserve every original pixel outside the
    registered Japanese regions. If a later editor import changes other labels,
    ordinary full-region packing remains available.
    """
    basis = record.get("stable_packing_basis")
    if not basis:
        return encode_vq_regions(original, image, all_regions)
    if hashlib.sha256(original).hexdigest() != basis["original_pvr_sha256"]:
        raise ValueError("Stable packing basis belongs to a different source texture")
    paths = [(project.root / basis[key]).resolve() for key in ("pvr", "png")]
    if any(not path.is_relative_to(project.root) for path in paths):
        raise ValueError("Stable packing basis must stay inside the project")
    prior = paths[0].read_bytes()
    if hashlib.sha256(prior).hexdigest() != basis["pvr_sha256"]:
        raise ValueError("Stable packing PVR changed after verification")
    if hashlib.sha256(paths[1].read_bytes()).hexdigest() != basis["png_sha256"]:
        raise ValueError("Stable packing source PNG changed after verification")
    with Image.open(paths[1]) as loaded:
        prior_source = np.asarray(loaded.convert("RGBA"))
    target = np.asarray(image.convert("RGBA"))
    source = np.asarray(decode_pvr(original))
    previous = np.asarray(decode_pvr(prior))
    if not (prior_source.shape == target.shape == source.shape == previous.shape):
        raise ValueError("Stable packing dimensions differ")
    p = original.find(b"PVRT")
    if len(prior) != len(original) or prior[:p+16] != original[:p+16]:
        raise ValueError("Stable packing header or length changed")
    allowed = np.zeros(target.shape[:2],bool)
    for x,y,w,h in all_regions:
        allowed[y:y+h,x:x+w] = True
    if not np.array_equal(previous[~allowed],source[~allowed]):
        raise ValueError("Stable packing basis changes original English or artwork")
    changed = np.zeros(target.shape[:2],bool)
    for x,y,w,h in basis["changed_regions"]:
        if any(v % 2 for v in (x,y,w,h)):
            raise ValueError("Stable packing regions must follow 2x2 VQ blocks")
        changed[y:y+h,x:x+w] = True
    if np.any(changed & ~allowed):
        raise ValueError("Stable packing region lies outside the Japanese labels")
    if not np.array_equal(prior_source[~changed],target[~changed]):
        packed, report = encode_vq_regions(original,image,all_regions)
        report["stable_basis_used"] = False
        report["stable_basis_reason"] = "A later image import also changed other labels"
        return packed, report
    packed, report = encode_vq_regions(prior,image,basis["changed_regions"])
    decoded = np.asarray(decode_pvr(packed))
    if not np.array_equal(decoded[~changed],previous[~changed]):
        raise AssertionError("Packing changed a previously approved unrelated label")
    report.update(stable_basis_used=True,previous_localized_pixels_outside_change_exact=True,
                  stable_basis_pvr_sha256=basis["pvr_sha256"])
    return packed, report


def pack_atlases(project: Project, disc) -> tuple[dict[str, Path], list[dict]]:
    entries = {e.name: e for e in disc.entries()}
    archives, reports, packed_members = {}, [], {}
    for item_id, record in sorted(project.edits("images").items()):
        if record.get("status") != "edited" or item_id.startswith("CPRO"):
            continue
        if record.get("text_matches_image") is False:
            raise ValueError(f"{item_id}: 변경한 문구가 그려진 수정 PNG를 가져오세요.")
        item = project.item("images", item_id)
        path = project.replacement("images", item_id)
        if not path.is_file():
            raise FileNotFoundError(path)
        name = item.get("archive") or item_id
        if name not in archives:
            entry = entries[name]
            archives[name] = bytearray(disc.read(entry.lba, entry.size))
        offset = item.get("offset", 0)
        original = project.disc_bytes(name, offset, item["size"])
        with Image.open(path) as image:
            image = image.convert("RGBA")
        regions = record.get("edit_regions") or [[0, 0, item["width"], item["height"]]]
        before = np.asarray(decode_pvr(original))
        after = np.asarray(image)
        if before.shape != after.shape:
            raise ValueError(f"Image dimensions differ: {item_id}")
        allowed = np.zeros(before.shape[:2], dtype=bool)
        for x, y, w, h in regions:
            allowed[y:y + h, x:x + w] = True
        if record.get('packing_mode') != 'common_uncompressed' and np.any(before[~allowed] != after[~allowed]):
            raise ValueError(f"{item_id}: registered Japanese regions 밖에 수정된 픽셀이 있습니다.")
        if record.get('packing_mode') == 'common_uncompressed':
            if item_id != 'COMMON_DATA.PVM:114':
                raise ValueError('Expanded common atlas mode is limited to game02')
            packed,report=encode_common_atlas(original,image,regions)
            # PVMH texture metadata mirrors the PVRT pixel/data formats.
            archives[name][12+item['index']*38+31]=1
        elif record.get("packing_mode") == "lossless_twiddled":
            if item_id != "0GDTEX.PVR":
                raise ValueError("Lossless relocation is limited to the disc-selection artwork")
            packed, report = encode_lossless_artwork(original, image, regions)
        else:
            packed, report = encode_stable_regions(project, original, image, record, regions)
        packed_members.setdefault(name,[]).append((offset,item['size'],packed))
        report.update(id=item_id, archive=name, pvr_sha256=hashlib.sha256(packed).hexdigest())
        reports.append(report)
        preview = project.root / "work/packed-images" / (safe_name(item_id) + ".png")
        preview.parent.mkdir(parents=True, exist_ok=True)
        decode_pvr(packed).save(preview)
    output = project.root / "assets/pvm-edits"
    output.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, raw in archives.items():
        # Growing one member must not shift the offsets of later edits before
        # those edits are applied. Original offsets remain catalog coordinates.
        for offset,size,packed in sorted(packed_members[name],reverse=True):
            raw[offset:offset+size]=packed
        path = output / name
        path.write_bytes(raw)
        paths[name] = path
    return paths, reports
