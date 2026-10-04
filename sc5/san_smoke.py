"""Focused SAN encoder and native frame-edit workflow validation."""
import csv
import json
from pathlib import Path
import shutil
import time
import tkinter as tk
import traceback
import uuid

import numpy as np

from .editor_project import Project
from .disc import GDImage
from .san import decode_san_frame, encode_san_regions
from .build_san import pack_animations, validate_archive


def run_san_review(root, disc=None):
    root = Path(root).resolve()
    result = {"success": False, "checks": []}
    original_edits = (root / "data/edits.json").read_bytes()
    editor = window = None
    try:
        from .native_editor import Editor
        source = Project(root, disc)
        key = "SANDATA_R4.AFS:006"
        item = source.item("animations", key)
        raw = source.disc_bytes(item["archive"], item["offset"], item["size"])
        decoded = decode_san_frame(raw)
        assert encode_san_regions(raw, 0, decoded, [])[0] == raw
        for frame, regions in ((0, [[1, 0, 2, 2]]), (4, [[0, 0, 2, 2]])):
            try:
                encode_san_regions(raw, frame, decoded, regions)
            except (ValueError, IndexError):
                pass
            else:
                raise AssertionError("Invalid SAN grid or frame accepted")
        outside = decoded.copy()
        pixel = outside.getpixel((0, 0))
        outside.putpixel((0, 0), ((pixel[0] + 1) % 256, pixel[1], pixel[2]))
        try:
            encode_san_regions(raw, 0, outside, [[120, 104, 72, 8]])
        except ValueError:
            pass
        else:
            raise AssertionError("Unapproved pixel change accepted")
        result["checks"].append("SAN_no_edit_byte_identity_and_invalid_frame_grid_region_refusal")

        fixture = root / "work" / ("san-review-fixture-" + uuid.uuid4().hex[:8])
        (fixture / "data").mkdir(parents=True)
        for name in ("edits.json", "disc.json", "images.json", "media.json", "animations.json", "text_review.jsonl"):
            shutil.copyfile(root / "data" / name, fixture / "data" / name)
        for folder in ("asr", "asr-refined/medium"):
            shutil.copytree(root / "data" / folder, fixture / "data" / folder)
        fp = Project(fixture, source.disc)
        for frame in range(4):
            path = fp.replacement("animations", key, frame)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source.replacement("animations", key, frame), path)
        with GDImage(source.disc) as image:
            paths, reports = pack_animations(fp, image)
        assert len(reports) == 1 and len(reports[0]["frames"]) == 4
        original_afs = source.disc_bytes(item["archive"])
        packed_afs = paths[item["archive"]].read_bytes()
        offset, end = item["offset"], item["offset"] + item["size"]
        assert len(original_afs) == len(packed_afs)
        assert original_afs[:offset] == packed_afs[:offset] and original_afs[end:] == packed_afs[end:]
        assert original_afs[offset:offset + 64] == packed_afs[offset:offset + 64]
        assert all(frame["outside_regions_exact"] for frame in reports[0]["frames"])
        result["checks"].append("four_frames_packed_with_San_header_other_AFS_members_and_outside_pixels_retained")
        archive_report = validate_archive(original_afs, packed_afs, item["archive"])
        assert archive_report["changed_SAN_members"] == 1
        for pos in (0, offset + 12):
            corrupt = bytearray(packed_afs); corrupt[pos] ^= 1
            try:
                validate_archive(original_afs, bytes(corrupt), item["archive"])
            except ValueError:
                pass
            else:
                raise AssertionError("Changed AFS directory or SAN header accepted")
        result["checks"].append("same_length_SAN_AFS_layout_validation_and_invalid_header_refusal")

        window = tk.Tk(); window.withdraw()
        editor = Editor(window, fp)
        def wait(predicate):
            deadline = time.monotonic() + 30
            while not predicate():
                window.update()
                if time.monotonic() > deadline:
                    raise TimeoutError("SAN native preview did not load")
                time.sleep(.02)
            window.update()
        editor.switch("animations", force=True)
        editor.pick(key)
        wait(lambda: editor.before.original is not None and editor.after.original is not None)
        assert len(editor.image_jp.get("1.0", "end-1c").splitlines()) == 8
        assert len(editor.image_ko.get("1.0", "end-1c").splitlines()) == 8
        editor.frame_index.set(4); editor.frame_changed()
        expected = fp.san_frame(key, 3).tobytes()
        wait(lambda: editor.before.original.tobytes() == expected)
        result["checks"].append("native_SAN_frame_selection_original_replacement_and_eight_editable_labels")

        lines = editor.image_ko.get("1.0", "end-1c").splitlines()
        lines[0] += " 수정"
        editor.image_ko.delete("1.0", "end"); editor.image_ko.insert("1.0", "\n".join(lines))
        assert editor.save_current()
        record = fp.edits("animations")[key]
        assert record["text_matches_frames"]["0"] is False
        assert all(record["text_matches_frames"][str(frame)] for frame in (1, 2, 3))
        with GDImage(source.disc) as image:
            try:
                pack_animations(fp, image)
            except ValueError:
                pass
            else:
                raise AssertionError("Changed label built without updated PNG")
        result["checks"].append("edited_text_blocks_build_until_affected_frame_PNG_import")

        labels = fp.edits("animations")[key]["labels"]
        labels[1] = labels[1] | {"korean": labels[1]["korean"] + " 수정"}
        fp.save_record("animations", key, {"labels": labels})
        fp.import_image("animations", key, source.replacement("animations", key, 0), 0)
        record = fp.edits("animations")[key]
        assert record["text_matches_frames"]["0"] is True
        assert record["text_matches_frames"]["1"] is False and record["text_matches_image"] is False
        fp.import_image("animations", key, source.replacement("animations", key, 1), 1)
        assert fp.edits("animations")[key]["text_matches_image"] is True
        result["checks"].append("import_confirms_only_selected_frame_and_retains_other_pending_text")

        export = fixture / "san-text.csv"
        fp.export_text(export)
        with export.open(encoding="utf-8-sig", newline="") as stream:
            rows = [row for row in csv.DictReader(stream) if row["kind"] == "animation_text"]
        assert len(rows) == 8 and {row["frame"] for row in rows} == {"1", "2", "3", "4"}
        assert all(row["id"] == key and row["japanese"] and row["korean"] for row in rows)
        result["checks"].append("SAN_text_CSV_preserves_source_translation_and_one_based_frame")
        result.update(success=True, fixture=str(fixture), packed_reports=reports)
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if editor:
            editor.close(force=True)
        elif window:
            window.destroy()
        result["original_edits_unchanged"] = (root / "data/edits.json").read_bytes() == original_edits
        if not result["original_edits_unchanged"]:
            result["success"] = False
    return result
