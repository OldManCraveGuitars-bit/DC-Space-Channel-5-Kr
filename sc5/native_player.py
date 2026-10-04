"""Tk video canvas with Windows PCM output and an editable caption layer."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import time
import wave
import tkinter as tk
from tkinter import ttk

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

from .editor_project import captions_at


class WaveFormat(ctypes.Structure):
    _pack_ = 2
    _fields_ = [("format", wintypes.WORD), ("channels", wintypes.WORD),
                ("rate", wintypes.DWORD), ("bytes_per_second", wintypes.DWORD),
                ("alignment", wintypes.WORD), ("bits", wintypes.WORD),
                ("extra", wintypes.WORD)]


class WaveHeader(ctypes.Structure):
    _fields_ = [("data", ctypes.c_void_p), ("length", wintypes.DWORD),
                ("recorded", wintypes.DWORD), ("user", ctypes.c_size_t),
                ("flags", wintypes.DWORD), ("loops", wintypes.DWORD),
                ("next", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]


class TimeUnion(ctypes.Union):
    _fields_ = [("samples", wintypes.DWORD), ("raw", ctypes.c_byte * 8)]


class MediaTime(ctypes.Structure):
    _fields_ = [("type", wintypes.UINT), ("value", TimeUnion)]


class WaveOutput:
    def __init__(self, path):
        with wave.open(str(path), "rb") as w:
            self.rate, self.channels, self.width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            self.pcm = w.readframes(w.getnframes())
        if self.width != 2:
            raise ValueError("16-bit PCM WAV is required")
        self.duration = len(self.pcm) / (self.rate * self.channels * self.width)
        self.api = ctypes.WinDLL("winmm")
        self.api.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
            ctypes.POINTER(WaveFormat), ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
        for name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
            getattr(self.api, name).argtypes = [ctypes.c_void_p, ctypes.POINTER(WaveHeader), wintypes.UINT]
        for name in ("waveOutReset", "waveOutClose", "waveOutPause", "waveOutRestart"):
            getattr(self.api, name).argtypes = [ctypes.c_void_p]
        self.api.waveOutGetPosition.argtypes = [ctypes.c_void_p, ctypes.POINTER(MediaTime), wintypes.UINT]
        self.handle = ctypes.c_void_p()
        self.buffer = self.header = None
        self.offset = 0.0

    def close(self):
        if self.handle.value:
            self.api.waveOutReset(self.handle)
            if self.header is not None:
                self.api.waveOutUnprepareHeader(self.handle, ctypes.byref(self.header), ctypes.sizeof(self.header))
            self.api.waveOutClose(self.handle)
            self.handle = ctypes.c_void_p()
        self.header = self.buffer = None

    def play(self, seconds):
        self.close()
        alignment = self.channels * self.width
        frame = min(round(seconds * self.rate), len(self.pcm) // alignment)
        self.offset = frame / self.rate
        pcm = self.pcm[frame * alignment:]
        if not pcm:
            return
        fmt = WaveFormat(1, self.channels, self.rate, self.rate * alignment, alignment, self.width * 8, 0)
        status = self.api.waveOutOpen(ctypes.byref(self.handle), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0)
        if status:
            raise RuntimeError(f"Windows 음성 출력 장치를 열 수 없습니다: {status}")
        self.buffer = ctypes.create_string_buffer(pcm)
        self.header = WaveHeader(data=ctypes.cast(self.buffer, ctypes.c_void_p), length=len(pcm))
        for name in ("waveOutPrepareHeader", "waveOutWrite"):
            status = getattr(self.api, name)(self.handle, ctypes.byref(self.header), ctypes.sizeof(self.header))
            if status:
                self.close()
                raise RuntimeError(f"PCM 재생 오류: {status}")

    def position(self):
        if not self.handle.value:
            return self.offset
        value = MediaTime(type=2)
        if self.api.waveOutGetPosition(self.handle, ctypes.byref(value), ctypes.sizeof(value)):
            return self.offset
        return self.offset + value.value.samples / self.rate

    def pause(self):
        if self.handle.value:
            self.api.waveOutPause(self.handle)

    def resume(self):
        if self.handle.value:
            self.api.waveOutRestart(self.handle)


class NativePlayer(ttk.Frame):
    def __init__(self, parent, font_path, segments, error_callback=None):
        super().__init__(parent)
        self.font_path = font_path
        self.caption_font = ImageFont.truetype(str(font_path), 22)
        self.segments = segments
        self.error_callback = error_callback or (lambda e: None)
        self.canvas = tk.Canvas(self, width=720, height=270, bg="#080c18", highlightthickness=0)
        self.canvas.pack(fill="x", expand=True)
        controls = ttk.Frame(self); controls.pack(fill="x", pady=4)
        self.play_button = ttk.Button(controls, text="재생", command=self.toggle)
        self.play_button.pack(side="left")
        for amount, label in ((-2, "−2초"), (-.25, "−0.25초"), (.25, "+0.25초"), (2, "+2초")):
            ttk.Button(controls, text=label, command=lambda a=amount: self.seek(self.position() + a)).pack(side="left", padx=2)
        self.time_label = ttk.Label(controls, text="0.000 / 0.000초"); self.time_label.pack(side="right")
        self.scale_value = tk.DoubleVar(value=0)
        self.scale = ttk.Scale(self, variable=self.scale_value, from_=0, to=1)
        self.scale.pack(fill="x")
        self.scale.bind("<ButtonPress-1>", lambda e: setattr(self, "dragging", True))
        self.scale.bind("<ButtonRelease-1>", self._slider_seek)
        self.audio = self.container = self.decoder = self.next_frame = self.video_frame = None
        self.waveform = None
        self.duration = self.offset = 0.0
        self.playing = self.dragging = False
        self.started = time.monotonic()
        self.photo = None
        self.closed = False
        self._timer = self.after(33, self.tick)

    def load(self, prepared):
        self.stop_media()
        self.duration = float(prepared.get("duration") or 0)
        if prepared.get("audio"):
            self.audio = WaveOutput(prepared["audio"])
            self.duration = self.duration or self.audio.duration
        if prepared.get("video"):
            self.container = av.open(str(prepared["video"]))
            self.decoder = iter(self.container.decode(video=0))
            self.next_frame = next(self.decoder, None)
        elif self.audio:
            samples = np.frombuffer(self.audio.pcm, dtype="<i2")[::self.audio.channels]
            parts = np.array_split(samples, min(900, len(samples)))
            peaks = [max(abs(int(a.min())), abs(int(a.max()))) / 32768 for a in parts if len(a)]
            self.waveform = peaks
        self.scale.configure(to=max(.001, self.duration))
        self.seek(0)

    def stop_media(self):
        self.playing = False
        if self.audio:
            self.audio.close()
        if self.container:
            self.container.close()
        self.audio = self.container = self.decoder = self.next_frame = self.video_frame = None
        self.waveform = None
        self.offset = 0
        self.play_button.configure(text="재생")

    def position(self):
        if self.playing:
            # Audio samples are the clock for voiced clips; M1V has no audio.
            if self.audio and self.audio.position() < self.audio.duration - .01:
                return min(self.duration, self.audio.position())
            return min(self.duration, self.offset + time.monotonic() - self.started)
        return self.offset

    def toggle(self):
        if self.duration <= 0:
            return
        if self.playing:
            self.offset = self.position()
            if self.audio:
                self.audio.pause()
            self.playing = False
            self.play_button.configure(text="재생")
        else:
            if self.offset >= self.duration - .005:
                self.seek(0)
            try:
                if self.audio:
                    self.audio.play(self.offset)
                self.started = time.monotonic()
                self.playing = True
                self.play_button.configure(text="일시 정지")
            except Exception as exc:
                self.error_callback(exc)

    def _slider_seek(self, event=None):
        self.dragging = False
        self.seek(self.scale_value.get())

    def seek(self, seconds):
        seconds = min(max(float(seconds), 0), self.duration)
        self.offset = seconds
        self.started = time.monotonic()
        if self.audio:
            if self.playing:
                self.audio.play(seconds)
            else:
                self.audio.close()
        if self.container:
            self.container.seek(round(seconds * av.time_base), backward=True)
            self.decoder = iter(self.container.decode(video=0))
            self.next_frame = next(self.decoder, None)
            self.video_frame = None
            self._advance_video(seconds)
        self.scale_value.set(seconds)
        self.draw(seconds)

    def _advance_video(self, seconds):
        for _ in range(240):
            if self.next_frame is None:
                break
            stamp = float(self.next_frame.time or 0)
            if stamp > seconds + .015:
                break
            self.video_frame = self.next_frame.to_image()
            self.next_frame = next(self.decoder, None)

    def draw(self, seconds):
        w = max(320, self.canvas.winfo_width())
        h = 270
        image = Image.new("RGB", (w, h), "#080c18")
        draw = ImageDraw.Draw(image)
        if self.video_frame is not None:
            frame = self.video_frame.copy(); frame.thumbnail((w, h), Image.Resampling.BILINEAR)
            image.paste(frame, ((w - frame.width) // 2, (h - frame.height) // 2))
        elif self.waveform:
            for index, peak in enumerate(self.waveform):
                x = round(index * (w - 30) / max(1, len(self.waveform) - 1)) + 15
                draw.line((x, 120 - peak * 75, x, 120 + peak * 75), fill="#8dc8e7")
            x = round(seconds / max(.001, self.duration) * (w - 30)) + 15
            draw.line((x, 20, x, 210), fill="#efbe66", width=2)
        segments = self.segments()
        caption = captions_at(segments, seconds, self.duration)
        if caption:
            font = self.caption_font
            lines = []
            for line in caption.splitlines():
                current = ""
                for char in line:
                    if current and font.getlength(current + char) > w - 40:
                        lines.append(current); current = ""
                    current += char
                lines.append(current)
            line_height = 28
            offsets = [float(s["bottom_offset"]) for s in segments
                       if "bottom_offset" in s and float(s.get("start", 0)) <= seconds < float(s.get("end", 0))
                       and s.get("korean", "").strip() and s.get("status") not in ("english_keep", "excluded", "no_change", "asr_hallucination")]
            content_height = frame.height if self.video_frame is not None else h
            content_bottom = (h + content_height) / 2
            bottom = content_bottom - max(offsets) * content_height / 480 if offsets else h - 12
            top = bottom - line_height * len(lines)
            self.last_caption_bounds = (12, max(0, top - 4), w - 12, bottom + 4)
            draw.rectangle((12, max(0, top - 4), w - 12, bottom + 4), fill="#101018")
            for i, line in enumerate(lines):
                draw.text((w // 2, top + i * line_height), line, anchor="mt", font=font,
                          fill="white", stroke_width=1, stroke_fill="black")
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.time_label.configure(text=f"{seconds:.3f} / {self.duration:.3f}초")

    def tick(self):
        if self.closed:
            return
        try:
            seconds = self.position()
            if self.playing and seconds >= self.duration - .001:
                self.offset = self.duration
                self.playing = False
                if self.audio:
                    self.audio.close()
                self.play_button.configure(text="재생")
            if self.decoder:
                self._advance_video(seconds)
            if not self.dragging:
                self.scale_value.set(seconds)
            self.draw(seconds)
        except Exception as exc:
            self.playing = False
            self.error_callback(exc)
        self._timer = self.after(33, self.tick)

    def destroy(self):
        self.closed = True
        self.after_cancel(self._timer)
        self.stop_media()
        super().destroy()
