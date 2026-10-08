"""Exercise the packaged native editor and media in a separate save fixture."""
from pathlib import Path
import hashlib
import json
import shutil
import time
import tkinter as tk
import traceback
import uuid
import wave

from PIL import Image

from .editor_project import Project, captions_at, timing_errors
from .media_decode import ffmpeg_run
from .native_player import WaveOutput


def run_caption_review(root, disc=None):
    """Check review choices through the editor, saved data and runtime export."""
    root = Path(root).resolve()
    result = {"success": False, "checks": [], "original_edits_unchanged": False}
    original_edits = (root / "data/edits.json").read_bytes()
    window = editor = None
    try:
        from .native_editor import Editor, SEGMENT_STATES
        from .runtime_config import export_runtime
        project = Project(root, disc)
        fixture = root / "work" / ("caption-review-fixture-" + uuid.uuid4().hex[:8])
        fixture.mkdir(parents=True)
        (fixture / "data").mkdir()
        for name in ("edits.json", "disc.json", "images.json", "media.json", "animations.json", "text_review.jsonl"):
            shutil.copyfile(root / "data" / name, fixture / "data" / name)
        (fixture / "data/asr").mkdir()
        shutil.copyfile(root / "data/asr/videos.jsonl", fixture / "data/asr/videos.jsonl")
        fp = Project(fixture, project.disc)
        original = fp.record("voices", "VOICEDATA.AFS:000")
        window = tk.Tk(); window.withdraw()
        editor = Editor(window, fp)
        errors = []
        editor.error = errors.append
        editor.switch("voices", force=True); editor.pick("VOICEDATA.AFS:000")
        started = time.monotonic()
        while editor.player.duration <= 0:
            window.update()
            if errors or time.monotonic() - started > 40:
                raise RuntimeError(errors or "Audio preview timed out")
            time.sleep(.015)
        window.update()
        editor.select_segment(0)
        editor.segment_state.set(SEGMENT_STATES["english_keep"])
        editor.segment_edited()
        midpoint = (float(editor.start.get()) + float(editor.end.get())) / 2
        assert captions_at(editor.live_segments(), midpoint, editor.duration) == ""
        assert editor.apply_segment()
        assert editor.segment_list.item("0", "values")[-1] == "영어 유지"
        result["checks"].append("English_keep_choice_excludes_live_preview")
        editor.select_segment(1)
        editor.segment_state.set(SEGMENT_STATES["reviewed"])
        editor.segment_edited()
        assert editor.save_current(), errors
        reloaded = Project(fixture, project.disc).record("voices", "VOICEDATA.AFS:000")
        assert reloaded["segments"][0]["status"] == "english_keep"
        assert reloaded["segments"][1]["status"] == "reviewed"
        assert [s["korean"] for s in reloaded["segments"]] == [s["korean"] for s in original["segments"]]
        result["checks"].append("Review_choices_persist_without_changing_translation")
        export_runtime(fp)
        config = json.loads((fixture / "work/runtime/config.json").read_text("utf-8"))
        exported = config["clips"]["VOICEDATA.AFS:0"]
        assert len(exported) == len(original["segments"]) - 1
        assert all(s["korean"] != original["segments"][0]["korean"] for s in exported)
        assert any(s["korean"] == original["segments"][1]["korean"] for s in exported)
        result["checks"].append("English_keep_excluded_and_reviewed_caption_exported")
        if "movie:r4_makuma.sfd" in config["clips"]:
            assert {s.get("bottom_offset") for s in config["clips"]["movie:r4_makuma.sfd"]} == {48}
            editor.switch("videos", force=True); editor.pick("R4_MAKUMA.SFD")
            started = time.monotonic()
            while editor.player.duration <= 0:
                window.update()
                if errors or time.monotonic() - started > 40:
                    raise RuntimeError(errors or "Video preview timed out")
                time.sleep(.015)
            window.update(); editor.player.seek(1)
            assert editor.player.last_caption_bounds[3] < 218
            editor.player.photo._PhotoImage__photo.write(str(fixture / "encoded-video-caption-preview.png"), format="png")
            result["checks"].append("Encoded_video_caption_offset_exported_and_preview_above_original_text")
        assert list((fixture / "work/editor-backups").rglob("edits.json"))
        result["checks"].append("Review_save_backup_created")
        result["fixture"] = str(fixture)
        result["success"] = True
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


def run(root, disc=None):
    root = Path(root).resolve()
    result = {"success": False, "checks": [], "original_edits_unchanged": False}
    window = editor = None
    original_edits = (root / "data/edits.json").read_bytes()
    try:
        from .native_editor import Editor
        project = Project(root, disc)
        counts = {k: len(project.catalog(k)) for k in ("text", "images", "voices", "videos", "animations")}
        result["catalogs"] = counts
        assert counts == {"text": 79, "images": 2013, "voices": 322, "videos": 146, "animations": 39}, counts
        result["checks"].append("all_catalogs_loaded")
        assert hashlib.sha256(project.font.read_bytes()).hexdigest() == "0cb7ee0dca070a387888bb03224bb3fed3ba73ae94078ac5cacf55c3bf477944"
        result["checks"].append("selected_font_exact")
        decoded = 0
        for item in project.catalog("animations"):
            for frame in range(item["frame_count"]):
                assert project.san_frame(item["id"], frame).size == (320, 240)
                decoded += 1
        assert decoded == 130
        result["san_frames_decoded"] = decoded
        result["checks"].append("all_SAN_frames_decoded")
        raw_segments = [{"start": 0, "end": 1, "korean": "첫 자막"}, {"start": 1, "end": 2, "korean": "다음 자막"}]
        assert captions_at(raw_segments, 1, 2) == "다음 자막"
        assert captions_at(raw_segments, 2, 2) == ""
        assert timing_errors([{"start": 0, "end": 6}], 5)
        assert timing_errors([{"start": float("nan"), "end": 2}], 5)
        result["checks"].append("caption_boundaries_and_invalid_times")
        check = ffmpeg_run(["-version"])
        assert check.returncode == 0
        result["checks"].append("bundled_ffmpeg_runs")
        fixture = root / "work" / ("native-smoke-fixture-" + uuid.uuid4().hex[:8])
        assert fixture.resolve().is_relative_to(root / "work")
        fixture.mkdir(parents=True)
        (fixture / "data").mkdir(exist_ok=True)
        for name in ("edits.json", "disc.json", "images.json", "media.json", "animations.json", "text_review.jsonl"):
            shutil.copyfile(root / "data" / name, fixture / "data" / name)
        (fixture / "data/asr").mkdir()
        shutil.copyfile(root / "data/asr/videos.jsonl", fixture / "data/asr/videos.jsonl")
        fp = Project(fixture, project.disc)
        stage = fp.record("images", "R11.PVM:000")
        stage_labels = [dict(label) for label in stage["labels"]]
        stage_labels[0]["korean"] = "긴급 뉴스"
        saved_stage = fp.save_record("images", "R11.PVM:000", {"labels": stage_labels})
        assert saved_stage["text_matches_image"] is True
        stage_before = fp.image("R11.PVM:000")
        stage_after = Image.open(fp.replacement("images", "R11.PVM:000"))
        for rectangle in ((0, 0, 26, 26), (182, 0, 208, 26), (0, 182, 512, 512)):
            assert stage_before.crop(rectangle).tobytes() == stage_after.crop(rectangle).tobytes()
        with Image.open(project.replacement("images", "R11.PVM:000")) as previous_stage:
            assert stage_after.crop((26, 0, 182, 26)).tobytes() != previous_stage.crop((26, 0, 182, 26)).tobytes()
        manual = stage_after.copy()
        stage_after.close()
        manual.putpixel((30, 8), (255, 255, 255, 255) if manual.getpixel((30, 8))[3] == 0 else (0, 0, 0, 0))
        imported = fixture / "manual-stage-caption.png"
        manual.save(imported)
        fp.import_image("images", "R11.PVM:000", imported)
        fp.save_record("images", "R11.PVM:000", {"labels": stage_labels, "note": "manual glyph adjustment retained"})
        with Image.open(fp.replacement("images", "R11.PVM:000")) as retained:
            assert retained.tobytes() == manual.tobytes()
        latin = fp.record("images", "R14.PVM:000")
        fp.save_record("images", "R14.PVM:000", {"labels": latin["labels"]})
        before_latin = fp.image("R14.PVM:000").crop((130, 26, 234, 52))
        after_latin = Image.open(fp.replacement("images", "R14.PVM:000")).crop((130, 26, 234, 52))
        assert before_latin.tobytes() == after_latin.tobytes()
        result["checks"].append("stage_caption_auto_render_manual_import_and_original_decoration_English_preserved")
        old = fp.record("text", "CPRO79.PVR")
        saved = fp.save_record("text", "CPRO79.PVR", {"japanese": old["japanese"], "korean": old["korean"],
            "fullwidth_advance": old["fullwidth_advance"], "status": "검수 중"})
        assert saved.get("source_review") == old.get("source_review")
        assert (fixture / "data/translations/CPRO79.txt").read_text(encoding="utf-8").strip() == saved["korean"]
        with Image.open(fp.replacement("images", "CPRO79.PVR")) as native:
            with Image.open(project.replacement("images", "CPRO79.PVR")) as existing:
                assert native.tobytes() == existing.tobytes()
        result["checks"].append("native_save_preserves_metadata_text_and_pixels")
        before = (fixture / "data/edits.json").read_bytes()
        try:
            fp.save_record("voices", "VOICEDATA.AFS:222", {"segments": [{"start": 0, "end": 27.8}], "status": "in_review"}, 5)
            raise AssertionError("Out-of-range captions were saved")
        except ValueError:
            pass
        assert (fixture / "data/edits.json").read_bytes() == before
        result["checks"].append("invalid_caption_save_rejected_without_changes")
        from .runtime_config import export_runtime
        fp.save_record("voices", "VOICEDATA.AFS:222", {"segments": [
            {"start": 1, "end": 2, "japanese": "みんな行くよ！", "korean": "모두 가자!"},
            {"start": 2, "end": 3, "japanese": "Let's dance!", "korean": "영어 번역 제외 확인"},
            {"start": 0, "end": 3, "japanese": "音声認識の誤り", "korean": "", "status": "asr_hallucination"},
        ]}, 5)
        export = export_runtime(fp)
        config = json.loads((fixture / "work/runtime/config.json").read_text("utf-8"))
        assert config["clips"]["VOICEDATA.AFS:222"] == [
            {"start": 1.0, "end": 2.0, "japanese": "みんな行くよ！", "korean": "모두 가자!"}]
        assert config["afs_bases"]["95645"] == "VOICEDATA.AFS"
        assert config["durations"]["VOICEDATA.AFS:222"] == 5
        assert config["caption_style"] == "box" and config["caption_box_alpha"] == 115
        assert any(s["reason"].startswith("Japanese source required") for s in export["skipped"])
        bad = fp.edits("voices")["VOICEDATA.AFS:222"]
        bad["segments"][0]["end"] = 8
        # Editing JSON externally must also be checked at the export boundary.
        edits = json.loads((fixture / "data/edits.json").read_text("utf-8"))
        edits["voices"]["VOICEDATA.AFS:222"] = bad
        fp._commit({fixture / "data/edits.json": json.dumps(edits, ensure_ascii=False).encode("utf-8")})
        previous_config = (fixture / "work/runtime/config.json").read_bytes()
        try:
            export_runtime(fp)
            raise AssertionError("Invalid saved Korean cue was exported")
        except ValueError:
            pass
        assert (fixture / "work/runtime/config.json").read_bytes() == previous_config
        result["checks"].append("runtime_export_keys_durations_English_exclusion_and_atomic_validation")
        result["fixture"] = str(fixture)
        window = tk.Tk(); window.withdraw()
        editor = Editor(window, project)
        window.update()
        def wait(predicate, timeout=40):
            start = time.monotonic()
            while not predicate():
                window.update()
                if time.monotonic() - start > timeout:
                    raise TimeoutError("Native preview did not load")
                time.sleep(.015)
            window.update()
        views = (("text", "CPRO79.PVR"), ("images", "0GDTEX.PVR"),
                 ("voices", "VOICEDATA.AFS:000"), ("videos", "DANRAN.SFD"),
                 ("animations", "SANDATA_R1.AFS:000"))
        for kind, item_id in views:
            editor.switch(kind, force=True)
            editor.pick(item_id)
            if kind in ("text", "images", "animations"):
                wait(lambda: editor.before.original is not None)
                assert editor.before.photo is not None
            else:
                wait(lambda: editor.player.duration > 0)
                editor.player.seek(min(.4, editor.player.duration / 2))
                assert editor.player.photo is not None
                if kind == "videos":
                    assert editor.player.video_frame is not None
                    assert editor.player.audio is not None
                result[kind + "_duration"] = editor.player.duration
            assert len(editor.list.get_children()) == counts[kind]
            result["checks"].append("native_view_" + kind)
        # Exercise the Windows device with silent PCM rather than a loud game clip.
        silence = fixture / "silence.wav"
        with wave.open(str(silence), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b"\0\0" * 3200)
        sound = WaveOutput(silence)
        try:
            sound.play(0); time.sleep(.08)
            pos = sound.position(); sound.pause(); sound.resume()
            result["windows_audio"] = {"opened": True, "position": pos}
            result["checks"].append("Windows_PCM_device_play_pause")
        finally:
            sound.close()
        result["success"] = True
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
