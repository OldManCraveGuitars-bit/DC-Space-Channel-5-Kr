"""Local review UI: editable scripts and timed subtitles, paired image previews."""
from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import subprocess
import threading
from urllib.parse import unquote, urlparse, parse_qs
import wave

from .assets import afs_members, decode_pvr, pvm_members
from .asr import decode_audio
from .cli import DEFAULT_DATA, DEFAULT_DISC, find_entry
from .disc import GDImage

ROOT = Path(__file__).resolve().parents[1]
EDITS = DEFAULT_DATA / "edits.json"
CACHE = ROOT / "work" / "preview-cache"
TRANSLATIONS = DEFAULT_DATA / "translations"
LOCK = threading.Lock()


def load_json(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def load_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def catalog(kind):
    if kind == "images":
        return load_json(DEFAULT_DATA / "images.json", [])
    if kind == "videos":
        video_asr = {x["id"]: x for x in load_lines(DEFAULT_DATA / "asr" / "videos.jsonl")}
        return [v | {"segments": video_asr.get(v["id"], {}).get("segments", [])}
                for v in load_json(DEFAULT_DATA / "media.json", {}).get("videos", [])]
    if kind == "voices":
        # Keep every AFS slot visible, including stage audio without ASR yet.
        asr = {}
        for path in sorted((DEFAULT_DATA / "asr").glob("*.jsonl")):
            if path.name != "videos.jsonl":
                asr.update({item["id"]: item for item in load_lines(path)})
        items = []
        for audio in load_json(DEFAULT_DATA / "media.json", {}).get("audio", []):
            if audio.get("kind") != "ADX":
                continue
            transcript = asr.get(audio["id"], {})
            item = audio | transcript
            item["segments"] = transcript.get("segments", [])
            item["status"] = transcript.get("status", "not_transcribed")
            item["has_asr"] = bool(transcript)
            # The ADX header is authoritative for the actual clip duration.
            if "duration" in audio:
                item["duration"] = audio["duration"]
            items.append(item)
        return items
    if kind == "text":
        return load_lines(DEFAULT_DATA / "text_review.jsonl")
    raise ValueError(kind)


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


class Handler(BaseHTTPRequestHandler):
    disc = DEFAULT_DISC

    def json_reply(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def file_reply(self, path, mime):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error_reply(self, error):
        self.json_reply({"error": str(error)}, 400)

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            route = parsed.path
            if route == "/":
                return self.file_reply(ROOT / "ui" / "index.html", "text/html; charset=utf-8")
            if route == "/font/blueroad":
                return self.file_reply(ROOT / "assets" / "fonts" / "yeongdeok-blueroad" /
                                       "Yeongdeok-Blueroad.ttf", "font/ttf")
            if route == "/api/catalog":
                kind = parse_qs(parsed.query).get("kind", [""])[0]
                return self.json_reply({"items": catalog(kind),
                                        "edits": load_json(EDITS, {}).get(kind, {})})
            if route.startswith("/api/image/"):
                item_id = unquote(route[len("/api/image/"):])
                return self.file_reply(self.image_path(item_id), "image/png")
            if route.startswith("/api/replacement/"):
                item_id = unquote(route[len("/api/replacement/"):])
                return self.file_reply(ROOT / "assets" / "image-edits" /
                                       (safe_name(item_id) + ".png"), "image/png")
            if route.startswith("/api/voice/"):
                item_id = unquote(route[len("/api/voice/"):])
                return self.file_reply(self.voice_path(item_id), "audio/wav")
            if route.startswith("/api/video/"):
                item_id = unquote(route[len("/api/video/"):])
                return self.file_reply(self.video_path(item_id), "video/mp4")
            self.send_error(404)
        except Exception as exc:
            self.error_reply(exc)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 30_000_000:
                raise ValueError("Upload exceeds 30 MB")
            body = json.loads(self.rfile.read(length))
            if self.path == "/api/save":
                kind, item_id = body["kind"], body["id"]
                if kind not in ("images", "videos", "voices", "text"):
                    raise ValueError("Unknown catalog")
                if kind == "text" and not re.fullmatch(r"CPRO\d{2}\.PVR", item_id):
                    raise ValueError("Unsupported text image")
                with LOCK:
                    edits = load_json(EDITS, {})
                    edits.setdefault(kind, {})[item_id] = body["value"]
                    EDITS.parent.mkdir(parents=True, exist_ok=True)
                    temp = EDITS.with_suffix(".tmp")
                    temp.write_text(json.dumps(edits, ensure_ascii=False, indent=2), encoding="utf-8")
                    temp.replace(EDITS)
                    if kind == "text":
                        TRANSLATIONS.mkdir(parents=True, exist_ok=True)
                        stem = item_id[:-4]
                        for suffix, key in ((".jp.txt", "japanese"), (".txt", "korean")):
                            target = TRANSLATIONS / (stem + suffix)
                            pending = Path(str(target) + ".tmp")
                            pending.write_text(body["value"].get(key, "").strip() + "\n", encoding="utf-8")
                            pending.replace(target)
                return self.json_reply({"saved": item_id})
            if self.path == "/api/render-text-image":
                item_id = body["id"]
                if not re.fullmatch(r"CPRO\d{2}\.PVR", item_id):
                    raise ValueError("Unsupported text image")
                record = load_json(EDITS, {}).get("text", {}).get(item_id, {})
                translation = record.get("korean", "").strip()
                if not translation:
                    raise ValueError("Korean translation is empty")
                from .render_cpro import render_blueroad_at_24
                policy = load_json(DEFAULT_DATA / "font_policy.json", {})
                overrides = policy.get("cpro_layout", {}).get("dense_card_overrides_px", {})
                advance = int(record.get("fullwidth_advance", overrides.get(item_id, 26)))
                image = render_blueroad_at_24(translation, advance)
                out = ROOT / "assets" / "image-edits" / (item_id + ".png")
                out.parent.mkdir(parents=True, exist_ok=True)
                pending = Path(str(out) + ".tmp")
                image.save(pending, format="PNG")
                pending.replace(out)
                return self.json_reply({"replacement": str(out)})
            if self.path == "/api/upload-image":
                item_id = body["id"]
                image = base64.b64decode(body["png_base64"], validate=True)
                from PIL import Image
                loaded = Image.open(io.BytesIO(image))
                loaded.verify()
                out = ROOT / "assets" / "image-edits" / (safe_name(item_id) + ".png")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(image)
                return self.json_reply({"replacement": str(out)})
            self.send_error(404)
        except Exception as exc:
            self.error_reply(exc)

    def image_path(self, item_id):
        out = CACHE / "images" / (safe_name(item_id) + ".png")
        if out.exists():
            return out
        item = next(i for i in catalog("images") if i["id"] == item_id)
        with GDImage(self.disc) as image:
            entry = find_entry(image, item["archive"] or item["id"])
            blob = image.read(entry.lba, entry.size)
            if item["archive"]:
                part = pvm_members(blob, entry.name)[item["index"]]
                blob = blob[part["offset"]:part["offset"] + part["size"]]
        out.parent.mkdir(parents=True, exist_ok=True)
        decode_pvr(blob).save(out)
        return out

    def voice_path(self, item_id):
        out = CACHE / "voices" / (safe_name(item_id) + ".wav")
        if out.exists():
            return out
        archive, index = item_id.split(":", 1)
        with GDImage(self.disc) as image:
            entry = find_entry(image, archive)
            blob = image.read(entry.lba, entry.size)
            part = afs_members(blob, archive)[int(index)]
            raw = blob[part["offset"]:part["offset"] + part["size"]]
        samples = decode_audio(raw)
        out.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes((samples.clip(-1, 1) * 32767).astype("<i2").tobytes())
        return out

    def video_path(self, item_id):
        out = CACHE / "videos" / (safe_name(item_id) + ".mp4")
        if out.exists():
            return out
        from imageio_ffmpeg import get_ffmpeg_exe
        source = CACHE / "videos" / item_id
        with GDImage(self.disc) as image:
            image.export(find_entry(image, item_id), source)
        cmd = [get_ffmpeg_exe(), "-y", "-v", "error", "-fflags", "+genpts",
               "-i", str(source), "-c:v", "libx264", "-preset", "ultrafast",
               "-pix_fmt", "yuv420p"]
        if item_id.upper().endswith(".SFD"):
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-an"]
        cmd += [str(out)]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr.decode("utf-8", "replace")[-500:])
        source.unlink()
        return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--disc", type=Path, default=DEFAULT_DISC)
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    Handler.disc = args.disc
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
