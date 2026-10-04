"""Project operations for the native editor; no HTTP server is used."""
from __future__ import annotations

import csv
from datetime import datetime
import io
import json
import math
from pathlib import Path
import re
import threading
import uuid
import wave

from PIL import Image

from .assets import decode_pvr
from .disc import GDImage
from .media_decode import decode_audio, ffmpeg_run
from .paths import resource_path
from .san import decode_san_frame


def read_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def read_lines(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()
            if s.strip()] if path.exists() else []


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def timing_errors(segments, duration=None):
    errors = {}
    for index, s in enumerate(segments):
        try:
            start, end = float(s["start"]), float(s["end"])
            if not math.isfinite(start) or not math.isfinite(end):
                raise ValueError()
            if start < 0 or end <= start:
                errors[index] = "시작은 0 이상, 끝은 시작보다 커야 합니다."
            elif duration is not None and end > duration + .005:
                errors[index] = f"실제 길이 {duration:.3f}초를 넘습니다."
        except (KeyError, TypeError, ValueError):
            errors[index] = "시작·끝 시간에 유효한 숫자를 입력하세요."
    return errors


def captions_at(segments, seconds, duration):
    if seconds < 0 or seconds >= duration:
        return ""
    lines = []
    for s in segments:
        if s.get("status") in {"excluded", "english_keep", "no_change", "asr_hallucination"}:
            continue
        try:
            start, end = float(s["start"]), float(s["end"])
            if math.isfinite(start) and math.isfinite(end) and start <= seconds < min(end, duration):
                if s.get("korean", "").strip():
                    lines.append(s["korean"].strip())
        except (KeyError, TypeError, ValueError):
            pass
    return "\n".join(lines)


class Project:
    def __init__(self, root, disc=None):
        self.root = Path(root).resolve()
        self.data = self.root / "data"
        if not (self.data / "edits.json").is_file():
            raise ValueError("data/edits.json이 있는 프로젝트 폴더를 선택하세요.")
        manifest = read_json(self.data / "disc.json", {})
        settings = read_json(self.data / "native_editor.json", {})
        self.disc = Path(disc or settings.get("disc") or manifest.get("source", ""))
        local_font = self.root / "assets/fonts/yeongdeok-blueroad/Yeongdeok-Blueroad.ttf"
        self.font = local_font if local_font.is_file() else resource_path(
            "assets/fonts/yeongdeok-blueroad/Yeongdeok-Blueroad.ttf")
        self.cache = self.root / "work/preview-cache"
        self.lock = threading.RLock()
        self._catalogs = {}

    def edits(self, kind):
        return read_json(self.data / "edits.json", {}).get(kind, {})

    def catalog(self, kind):
        if kind in self._catalogs:
            return self._catalogs[kind]
        media = read_json(self.data / "media.json", {})
        if kind == "text":
            items = read_lines(self.data / "text_review.jsonl")
        elif kind == "images":
            items = read_json(self.data / "images.json", [])
        elif kind == "animations":
            items = read_json(self.data / "animations.json", media.get("animations", []))
        elif kind in ("voices", "videos"):
            transcriptions = {}
            for file in sorted((self.data / "asr").glob("*.jsonl")):
                if (kind == "videos") == (file.name == "videos.jsonl"):
                    transcriptions.update({r["id"]: r for r in read_lines(file)})
            # The second voice analysis has sample-accurate timings. Keep the
            # first ASR files intact and let saved/manual edits take precedence.
            if kind == "voices":
                for row in read_lines(self.data / "asr-refined/medium/voices.jsonl"):
                    transcriptions[row["id"]] = row | {"asr_source": "asr-refined/medium/voices.jsonl"}
            source = media.get("videos" if kind == "videos" else "audio", [])
            items = []
            for item in source:
                if kind == "voices" and item.get("kind") != "ADX":
                    continue
                transcript = transcriptions.get(item["id"], {})
                merged = item | transcript | {"segments": transcript.get("segments", []),
                    "has_asr": bool(transcript), "status": transcript.get("status", "not_transcribed")}
                if "duration" in item:
                    merged["duration"] = item["duration"]
                items.append(merged)
        else:
            raise ValueError(kind)
        self._catalogs[kind] = items
        return items

    def item(self, kind, item_id):
        return next(x for x in self.catalog(kind) if x["id"] == item_id)

    def record(self, kind, item_id):
        original = self.item(kind, item_id)
        return original | self.edits(kind).get(item_id, {})

    def _commit(self, changes, backup=True):
        """Prepare every file before replacement; retain the previous version."""
        with self.lock:
            pending = {}
            originals = {}
            token = uuid.uuid4().hex
            backup_root = self.root / "work/editor-backups" / (datetime.now().strftime("%Y%m%d-%H%M%S-") + token[:8])
            try:
                for path, content in changes.items():
                    path = Path(path).resolve()
                    if not path.is_relative_to(self.root):
                        raise ValueError("Project output is outside the selected project")
                    originals[path] = path.read_bytes() if path.exists() else None
                    if backup and originals[path] is not None:
                        saved = backup_root / path.relative_to(self.root)
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        saved.write_bytes(originals[path])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temp = path.with_name(path.name + ".pending-" + token)
                    pending[path] = temp
                    temp.write_bytes(content)
                for path, temp in pending.items():
                    temp.replace(path)
            except Exception:
                for path, original in originals.items():
                    if original is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(original)
                raise
            finally:
                for temp in pending.values():
                    temp.unlink(missing_ok=True)

    def save_record(self, kind, item_id, value, duration=None):
        self.item(kind, item_id)  # Only catalogued IDs can produce files.
        if kind in ("voices", "videos"):
            errors = timing_errors(value.get("segments", []), duration)
            if errors:
                raise ValueError(f"자막 시간을 확인하세요: {len(errors)}개 오류")
        with self.lock:
            edits = read_json(self.data / "edits.json", {})
            previous = edits.setdefault(kind, {}).get(item_id, {})
            record = previous | value
            if kind == "images" and "labels" in value:
                old_labels = edits[kind].get(item_id, {}).get("labels", [])
                if old_labels and value["labels"] != old_labels:
                    record["text_matches_image"] = False
            elif kind == "animations" and "labels" in value:
                flags = dict(previous.get("text_matches_frames", {}))
                old_labels = previous.get("labels", [])
                for label in value["labels"]:
                    frame = label.get("frame")
                    if not isinstance(frame, int) or not 0 <= frame < self.item(kind, item_id)["frame_count"]:
                        raise ValueError("SAN 문구의 프레임 번호를 확인하세요.")
                if old_labels and old_labels != value["labels"]:
                    for frame in {label["frame"] for label in old_labels + value["labels"]}:
                        old = [x for x in old_labels if x["frame"] == frame]
                        new = [x for x in value["labels"] if x["frame"] == frame]
                        if old != new:
                            flags[str(frame)] = False
                record["text_matches_frames"] = flags | record.get("text_matches_frames", {})
                # Changed text always invalidates the affected frame even when
                # the caller copied earlier confirmation flags into its value.
                for frame, confirmed in flags.items():
                    if not confirmed:
                        record["text_matches_frames"][frame] = False
                record["text_matches_image"] = all(record["text_matches_frames"].values())
            edits[kind][item_id] = record
            changes = {}
            if (kind == "images" and record.get("renderer") == "stage_caption_atlas"
                    and "labels" in value
                    and (record.get("text_matches_image") is False
                         or not self.replacement(kind, item_id).is_file()
                         or previous.get("renderer") != "stage_caption_atlas")):
                from .texture_text import render_labels
                rendered = render_labels(self.image(item_id), record["labels"], self.font)
                png = io.BytesIO(); rendered.save(png, format="PNG")
                changes[self.replacement(kind, item_id)] = png.getvalue()
                record["text_matches_image"] = True
                record["edit_regions"] = [label["region"] for label in record["labels"]]
            if kind == "text":
                if not re.fullmatch(r"CPRO\d{2}\.PVR", item_id):
                    raise ValueError("Unsupported text record")
                from .render_cpro import render_blueroad_at_24
                if not record.get("japanese", "").strip() or not record.get("korean", "").strip():
                    raise ValueError("원문과 번역은 비울 수 없습니다.")
                rendered = render_blueroad_at_24(record["korean"], int(record.get("fullwidth_advance", 26)), self.font)
                png = io.BytesIO(); rendered.save(png, format="PNG")
                stem = item_id[:-4]
                for suffix, key in ((".jp.txt", "japanese"), (".txt", "korean")):
                    changes[self.data / "translations" / (stem + suffix)] = (record[key].strip() + "\n").encode("utf-8")
                    record[key] = record[key].strip()
                changes[self.root / "assets/image-edits" / (item_id + ".png")] = png.getvalue()
                image_record = edits.setdefault("images", {}).get(item_id, {})
                edits["images"][item_id] = image_record | {"status": "edited", "text_record": item_id}
            changes[self.data / "edits.json"] = (json.dumps(edits, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._commit(changes)
        return record

    def disc_bytes(self, name, offset=0, size=None):
        with GDImage(self.disc) as disc:
            entry = next(e for e in disc.entries() if e.name.upper() == name.upper())
            size = entry.size - offset if size is None else size
            if offset < 0 or size < 0 or offset + size > entry.size:
                raise ValueError("Invalid disc member extent")
            skip = offset % 2048
            return disc.read(entry.lba + offset // 2048, size + skip)[skip:]

    def image(self, item_id):
        item = self.item("images", item_id)
        name = item.get("archive") or item_id
        blob = self.disc_bytes(name, item.get("offset", 0), item["size"])
        return decode_pvr(blob)

    def replacement(self, kind, item_id, frame=0):
        if kind == "animations":
            return self.root / "assets/san-edits" / safe_name(item_id) / f"frame{frame:03d}.png"
        return self.root / "assets/image-edits" / (safe_name(item_id) + ".png")

    def san_frame(self, item_id, frame=0):
        item = self.item("animations", item_id)
        raw = self.disc_bytes(item["archive"], item["offset"], item["size"])
        return decode_san_frame(raw, frame)

    def import_image(self, kind, item_id, source, frame=0):
        item = self.item(kind, item_id)
        if kind == "animations" and not 0 <= frame < item["frame_count"]:
            raise ValueError("프레임 번호를 확인하세요.")
        with Image.open(source) as loaded:
            loaded.load()
            if loaded.size != (item["width"], item["height"]):
                raise ValueError(f"{item['width']}×{item['height']} PNG가 필요합니다.")
            out = io.BytesIO(); loaded.convert("RGBA").save(out, format="PNG")
        self._commit({self.replacement(kind, item_id, frame): out.getvalue()})
        value = {"status": "edited", "text_matches_image": True}
        if kind == "animations":
            flags = self.edits(kind).get(item_id, {}).get("text_matches_frames", {}) | {str(frame): True}
            value.update(text_matches_frames=flags, text_matches_image=all(flags.values()))
        self.save_record(kind, item_id, value)

    def voice_path(self, item_id):
        out = self.cache / "voices" / (safe_name(item_id) + ".wav")
        if out.is_file():
            return out
        item = self.item("voices", item_id)
        raw = self.disc_bytes(item["archive"], item["offset"], item["size"])
        samples = decode_audio(raw)
        # ADX decoders can add a few padding samples; retain the header duration.
        if item.get("duration"):
            samples = samples[:round(item["duration"] * 16000)]
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(".pending.wav")
        with wave.open(str(temp), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes((samples.clip(-1, 1) * 32767).astype("<i2").tobytes())
        temp.replace(out)
        return out

    def video_path(self, item_id):
        out = self.cache / "videos" / (safe_name(item_id) + ".mp4")
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        source = out.parent / (safe_name(item_id) + ".source")
        temp = out.with_suffix(".pending.mp4")
        with GDImage(self.disc) as disc:
            entry = next(e for e in disc.entries() if e.name.upper() == item_id.upper())
            disc.export(entry, source)
        try:
            args = ["-y", "-fflags", "+genpts", "-i", str(source), "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
            args += ["-c:a", "aac", "-b:a", "128k"] if item_id.upper().endswith(".SFD") else ["-an"]
            result = ffmpeg_run(args + [str(temp)])
            if result.returncode:
                raise ValueError(result.stderr.decode("utf-8", "replace")[-1000:])
            temp.replace(out)
        finally:
            source.unlink(missing_ok=True); temp.unlink(missing_ok=True)
        return out

    def prepare_media(self, kind, item_id):
        if kind == "voices":
            return {"video": None, "audio": self.voice_path(item_id),
                    "duration": self.item(kind, item_id).get("duration")}
        import av
        video = self.video_path(item_id)
        with av.open(str(video)) as container:
            duration = container.duration / av.time_base if container.duration else 0
            audio_present = bool(container.streams.audio)
        audio = self.cache / "videos" / (safe_name(item_id) + ".audio.wav")
        if audio_present and not audio.is_file():
            temp = audio.with_suffix(".pending.wav")
            result = ffmpeg_run(["-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temp)])
            if result.returncode:
                raise ValueError(result.stderr.decode("utf-8", "replace")[-1000:])
            temp.replace(audio)
        return {"video": video, "audio": audio if audio_present else None, "duration": duration}

    def export_text(self, output):
        count = 0
        with Path(output).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("kind", "id", "segment", "start", "end", "japanese", "korean", "status", "frame"))
            writer.writeheader()
            for kind in ("text", "voices", "videos"):
                edits = self.edits(kind)
                for item in self.catalog(kind):
                    r = item | edits.get(item["id"], {})
                    if kind == "text":
                        writer.writerow({"kind": kind, "id": item["id"], **{k: r.get(k, "") for k in ("japanese", "korean", "status")}})
                        count += 1
                    else:
                        for index, segment in enumerate(r.get("segments", [])):
                            writer.writerow({"kind": kind, "id": item["id"], "segment": index, **{k: segment.get(k, "") for k in ("start", "end", "japanese", "korean", "status")}})
                            count += 1
            for item in self.catalog("images"):
                record = item | self.edits("images").get(item["id"], {})
                for index, label in enumerate(record.get("labels", [])):
                    writer.writerow({"kind": "image_text", "id": item["id"], "segment": index,
                                     "japanese": label.get("japanese", ""), "korean": label.get("korean", ""),
                                     "status": record.get("status", "")})
                    count += 1
            for item in self.catalog("animations"):
                record = item | self.edits("animations").get(item["id"], {})
                for index, label in enumerate(record.get("labels", [])):
                    writer.writerow({"kind": "animation_text", "id": item["id"], "segment": index,
                                     "frame": label["frame"] + 1, "japanese": label.get("japanese", ""),
                                     "korean": label.get("korean", ""), "status": record.get("status", "")})
                    count += 1
        return count
