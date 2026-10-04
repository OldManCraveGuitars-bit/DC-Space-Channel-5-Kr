"""Standalone Windows localization editor, using Tk rather than a browser."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from .editor_project import Project, read_json, timing_errors
from .native_player import NativePlayer
from .paths import project_root

TABS = {"text": "원문·번역", "images": "이미지 비교", "voices": "음성·자막",
        "videos": "영상·자막", "animations": "SAN 프레임"}
STATES = {"unreviewed": "미검수", "korean_needed": "한글화 필요", "english_keep": "영어 유지",
          "no_change": "수정 불필요", "edited": "수정본 준비", "not_transcribed": "음성 인식 대기",
          "needs_listening": "청취 검수 필요", "in_review": "검수 중", "decode_pending": "미검수"}
SEGMENT_STATES = {"unreviewed": "미검수", "literal_draft": "번역 초안", "needs_listening": "청취 검수 필요",
                  "english_keep": "영어 유지", "asr_hallucination": "인식 오류", "manual": "직접 수정",
                  "reviewed": "검수 완료"}


class Picture(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent)
        ttk.Label(self, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 4))
        self.canvas = tk.Canvas(self, width=405, height=244, background="#202838", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.original = self.photo = None
        self.zoom = "맞춤"
        self.crop = False
        self.canvas.bind("<Configure>", lambda e: self.redraw())

    def set(self, image, crop=False):
        self.original = image.copy() if image is not None else None
        self.crop = crop
        self.redraw()

    def redraw(self):
        self.canvas.delete("all")
        if self.original is None:
            self.canvas.create_text(200, 110, text="이미지 없음", fill="#b2bdd0")
            return
        image = self.original.convert("RGBA")
        if self.crop:
            image = image.crop((0, 0, 384, 244))
        w, h = max(200, self.canvas.winfo_width()), max(100, self.canvas.winfo_height())
        scale = min(w / image.width, h / image.height) if self.zoom == "맞춤" else float(self.zoom.rstrip("%")) / 100
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.NEAREST)
        backdrop = Image.new("RGBA", image.size, "#303c4b")
        draw = ImageDraw.Draw(backdrop)
        for y in range(0, image.height, 16):
            for x in range(0, image.width, 16):
                if (x // 16 + y // 16) % 2:
                    draw.rectangle((x, y, x + 15, y + 15), fill="#3e4c60")
        backdrop.alpha_composite(image)
        self.photo = ImageTk.PhotoImage(backdrop)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, image.width, image.height))
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))


class Editor:
    def __init__(self, root, project):
        self.window = root
        self.project = project
        self.kind = "text"
        self.selected = None
        self.items = []
        self.player = None
        self.dirty = False
        self.loading = False
        self.generation = 0
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.events = queue.Queue()
        self.closed = False
        self.window.title("Space Channel 5 한글화 편집기")
        self.window.geometry("1340x930")
        self.window.minsize(1080, 760)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background="#192230", foreground="#e8eef7", fieldbackground="#253246", font=("맑은 고딕", 10))
        style.configure("Treeview", background="#202b3c", fieldbackground="#202b3c", rowheight=29)
        style.map("Treeview", background=[("selected", "#4d547e")])
        style.configure("TButton", padding=(10, 5))
        style.configure("Heading.TLabel", font=("맑은 고딕", 11, "bold"))
        style.configure("Error.TLabel", foreground="#ffb0a8")
        root.configure(background="#192230")
        header = ttk.Frame(root, padding=12); header.pack(fill="x")
        ttk.Label(header, text="Space Channel 5 일본판 · 한글화 편집기", style="Heading.TLabel").pack(anchor="w")
        self.project_label = ttk.Label(header, text=str(project.root)); self.project_label.pack(anchor="w", pady=3)
        toolbar = ttk.Frame(header); toolbar.pack(fill="x")
        for label, action in (("프로젝트 선택", self.choose_project), ("원본 디스크 선택", self.choose_disc),
                              ("번역·자막 CSV 내보내기", self.export_csv), ("게임 자막 반영", self.export_runtime),
                              ("자막 내장 ROM 생성", self.build_disc), ("자막 내장 ROM 실행", self.launch_player)):
            ttk.Button(toolbar, text=label, command=action).pack(side="left", padx=(0, 6))
        ttk.Label(header, text="폰트: 영덕 블루로드체 · 영어 표기 유지 · 일본어 원문에 충실하게 번역").pack(anchor="w", pady=(7, 0))
        caption_controls = ttk.Frame(header); caption_controls.pack(fill="x", pady=(5, 0))
        ttk.Label(caption_controls, text="게임 자막 표시:").pack(side="left", padx=(0, 6))
        caption_config = read_json(project.root / "work/runtime/config.json", {})
        selected_style = caption_config.get("caption_style", "box")
        self.caption_style = tk.StringVar(value="검은 배경" if selected_style == "box" else "검정 테두리")
        style_picker = ttk.Combobox(caption_controls, textvariable=self.caption_style,
                                   values=("검은 배경",), state="readonly", width=14)
        style_picker.pack(side="left")
        style_picker.bind("<<ComboboxSelected>>", self.set_caption_style)
        ttk.Label(caption_controls, text="  배경 농도:").pack(side="left", padx=(6, 3))
        self.caption_opacity = tk.StringVar(value=str(round(caption_config.get("caption_box_alpha", 115) * 100 / 255)))
        ttk.Spinbox(caption_controls, from_=0, to=100, increment=5, width=5,
                    textvariable=self.caption_opacity).pack(side="left")
        ttk.Label(caption_controls, text="% (낮을수록 투명)").pack(side="left", padx=4)
        ttk.Button(caption_controls, text="적용", command=self.set_caption_style).pack(side="left", padx=4)
        tabs = ttk.Frame(root, padding=(12, 0)); tabs.pack(fill="x")
        self.tab_buttons = {}
        for kind, title in TABS.items():
            button = ttk.Button(tabs, text=title, command=lambda k=kind: self.switch(k))
            button.pack(side="left", padx=(0, 5)); self.tab_buttons[kind] = button
        panes = ttk.Panedwindow(root, orient="horizontal"); panes.pack(fill="both", expand=True, padx=12, pady=10)
        sidebar = ttk.Frame(panes, width=280); panes.add(sidebar, weight=1)
        self.search = tk.StringVar()
        search_box = ttk.Entry(sidebar, textvariable=self.search); search_box.pack(fill="x", pady=(0, 5))
        search_box.bind("<KeyRelease>", lambda e: self.render_list())
        self.count = ttk.Label(sidebar); self.count.pack(anchor="w", pady=4)
        listing = ttk.Frame(sidebar); listing.pack(fill="both", expand=True)
        self.list = ttk.Treeview(listing, columns=("status",), show="tree headings", selectmode="browse")
        self.list.heading("#0", text="파일 / 번역 제목"); self.list.heading("status", text="상태")
        self.list.column("#0", width=210, minwidth=130); self.list.column("status", width=100, minwidth=65)
        bar = ttk.Scrollbar(listing, command=self.list.yview); self.list.configure(yscrollcommand=bar.set)
        self.list.pack(side="left", fill="both", expand=True); bar.pack(side="right", fill="y")
        self.list.bind("<<TreeviewSelect>>", self.on_pick)
        self.list.tag_configure("draft", foreground="#f1c879")
        self.list.tag_configure("reviewed", foreground="#a5d9b4")
        detail = ttk.Frame(panes); panes.add(detail, weight=4)
        self.detail_canvas = tk.Canvas(detail, bg="#192230", highlightthickness=0)
        bar = ttk.Scrollbar(detail, command=self.detail_canvas.yview)
        self.detail_canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y"); self.detail_canvas.pack(side="left", fill="both", expand=True)
        self.detail = ttk.Frame(self.detail_canvas, padding=8)
        self.detail_handle = self.detail_canvas.create_window((0, 0), window=self.detail, anchor="nw")
        self.detail.bind("<Configure>", lambda e: self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all")))
        self.detail_canvas.bind("<Configure>", lambda e: self.detail_canvas.itemconfigure(self.detail_handle, width=e.width))
        self.detail_canvas.bind("<MouseWheel>", lambda e: self.detail_canvas.yview_scroll(-int(e.delta / 120), "units"))
        self.status = tk.StringVar(value="준비됨")
        ttk.Label(root, textvariable=self.status, padding=(12, 5)).pack(fill="x")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Control-s>", lambda e: self.save_current())
        self.window.bind("<Control-f>", lambda e: search_box.focus_set())
        self.window.bind("<Control-space>", lambda e: self.player.toggle() if self.player else None)
        self._pump_timer = root.after(60, self.pump)
        self.switch("text", force=True)

    def message(self, text):
        self.status.set(text)

    def error(self, error):
        self.message("오류: " + str(error))
        messagebox.showerror("작업 오류", str(error), parent=self.window)

    def mark_dirty(self, event=None):
        if not self.loading:
            self.dirty = True
            self.message("수정 내용이 있습니다. Ctrl+S로 저장하세요.")

    def text_widget(self, parent, height=8):
        widget = tk.Text(parent, height=height, wrap="word", undo=True, font=("맑은 고딕", 11),
                         bg="#253246", fg="#f3f6fc", insertbackground="white", relief="flat", padx=8, pady=5)
        widget.bind("<KeyRelease>", self.mark_dirty)
        return widget

    def leave(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("저장되지 않은 내용", "변경 내용을 저장할까요?", parent=self.window)
        if answer is None:
            return False
        return self.save_current() if answer else True

    def switch(self, kind, force=False):
        if not force and not self.leave():
            return
        self.generation += 1
        self.kind, self.selected, self.dirty = kind, None, False
        self.items = self.project.catalog(kind)
        self.search.set("")
        for k, button in self.tab_buttons.items():
            button.configure(text=("● " if k == kind else "") + TABS[k])
        self.clear_detail()
        self.render_list()
        ttk.Label(self.detail, text="목록에서 항목을 선택하세요.").pack(anchor="w")

    def render_list(self):
        self.loading = True
        self.list.delete(*self.list.get_children())
        query = self.search.get().strip().casefold()
        edits = self.project.edits(self.kind)
        visible = 0
        for item in self.items:
            r = item | edits.get(item["id"], {})
            if query and query not in json.dumps(r, ensure_ascii=False).casefold():
                continue
            title = (r.get("korean", "").splitlines() or [""])[0] if self.kind == "text" else r.get("name", "")
            label = item["id"] + ((" · " + title) if title and title != item["id"] else "")
            state = r.get("status", "unreviewed")
            self.list.insert("", "end", iid=item["id"], text=label, values=(STATES.get(state, state),),
                tags=("reviewed" if state in ("완료", "edited", "no_change", "english_keep") else "draft",))
            visible += 1
        self.count.configure(text=f"검색 {visible}개 / 전체 {len(self.items)}개")
        if self.selected and self.list.exists(self.selected):
            self.list.selection_set(self.selected)
        self.loading = False

    def on_pick(self, event=None):
        selection = self.list.selection()
        if self.loading or not selection or selection[0] == self.selected:
            return
        if not self.leave():
            if self.selected and self.list.exists(self.selected):
                self.list.selection_set(self.selected)
            return
        self.pick(selection[0])

    def clear_detail(self):
        if self.player:
            self.player.destroy(); self.player = None
        for child in self.detail.winfo_children():
            child.destroy()
        self.detail_canvas.yview_moveto(0)

    def pick(self, item_id):
        self.generation += 1
        self.selected = item_id
        self.clear_detail()
        self.loading = True
        self.current = self.project.record(self.kind, item_id)
        self.dirty = False
        ttk.Label(self.detail, text=item_id, style="Heading.TLabel").pack(anchor="w", pady=(0, 5))
        if self.kind == "text":
            self.show_text()
        elif self.kind in ("images", "animations"):
            self.show_image()
        else:
            self.show_media()
        self.loading = False
        self.message("불러오는 중…")

    def async_job(self, operation, callback, description, guard=True):
        token = self.generation if guard else None
        self.message(description)
        future = self.pool.submit(operation)
        def finished(f):
            try:
                self.events.put((token, callback, f.result(), None))
            except Exception as error:
                self.events.put((token, callback, None, error))
        future.add_done_callback(finished)

    def pump(self):
        if self.closed:
            return
        while not self.events.empty():
            token, callback, result, error = self.events.get()
            if token is not None and token != self.generation:
                continue
            if error:
                self.error(error)
            else:
                try:
                    callback(result)
                except Exception as error:
                    self.error(error)
        self._pump_timer = self.window.after(60, self.pump)

    def pair(self):
        toolbar = ttk.Frame(self.detail); toolbar.pack(fill="x")
        ttk.Label(toolbar, text="표시 크기").pack(side="left")
        self.zoom = tk.StringVar(value="맞춤")
        combo = ttk.Combobox(toolbar, textvariable=self.zoom, values=("맞춤", "50%", "100%", "200%"), state="readonly", width=7)
        combo.pack(side="left", padx=5)
        ttk.Label(toolbar, text="확대 이미지: 마우스로 끌어 이동").pack(side="left")
        pair = ttk.Frame(self.detail); pair.pack(fill="x", pady=6)
        pair.columnconfigure(0, weight=1); pair.columnconfigure(1, weight=1)
        self.before = Picture(pair, "일본판 원본"); self.before.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.after = Picture(pair, "한글 수정본 / 미리보기"); self.after.grid(row=0, column=1, sticky="nsew")
        def zoomed(e=None):
            for picture in (self.before, self.after):
                picture.zoom = self.zoom.get(); picture.redraw()
        combo.bind("<<ComboboxSelected>>", zoomed)

    def load_pair(self, frame=0):
        kind, item_id, project = self.kind, self.selected, self.project
        def operation():
            original = project.san_frame(item_id, frame) if kind == "animations" else project.image(item_id)
            target = project.replacement(kind, item_id, frame)
            replacement = None
            if target.exists():
                with Image.open(target) as image:
                    replacement = image.copy()
            return original, replacement
        def loaded(images):
            self.before.set(images[0], crop=kind == "text")
            self.after.set(images[1], crop=kind == "text")
            self.message("원본·수정본 비교 준비됨")
        self.async_job(operation, loaded, "이미지를 읽는 중…")

    def show_text(self):
        self.pair()
        columns = ttk.Frame(self.detail); columns.pack(fill="x")
        columns.columnconfigure(0, weight=1); columns.columnconfigure(1, weight=1)
        ttk.Label(columns, text="일본어 원문").grid(row=0, column=0, sticky="w")
        ttk.Label(columns, text="한글 번역").grid(row=0, column=1, sticky="w")
        self.jp = self.text_widget(columns, 10); self.jp.grid(row=1, column=0, sticky="ew", padx=(0, 7))
        self.ko = self.text_widget(columns, 10); self.ko.grid(row=1, column=1, sticky="ew")
        self.jp.insert("1.0", self.current.get("japanese", self.current.get("source", "")))
        self.ko.insert("1.0", self.current.get("korean", ""))
        controls = ttk.Frame(self.detail); controls.pack(fill="x", pady=10)
        ttk.Label(controls, text="한글 간격").pack(side="left")
        self.advance = tk.StringVar(value=str(self.current.get("fullwidth_advance", 26)))
        spacing = ttk.Combobox(controls, textvariable=self.advance, values=("24", "25", "26"), state="readonly", width=4)
        spacing.pack(side="left", padx=(4, 12)); spacing.bind("<<ComboboxSelected>>", self.mark_dirty)
        self.state = tk.StringVar(value=self.current.get("status", "번역 초안"))
        state = ttk.Combobox(controls, textvariable=self.state, values=("미검수", "번역 초안", "검수 중", "완료", "영어 유지"), state="readonly", width=10)
        state.pack(side="left"); state.bind("<<ComboboxSelected>>", self.mark_dirty)
        ttk.Button(controls, text="자동 줄바꿈", command=self.wrap_text).pack(side="left", padx=6)
        ttk.Button(controls, text="미리보기", command=self.preview_text).pack(side="left")
        ttk.Button(controls, text="저장·시안 생성 (Ctrl+S)", command=self.save_current).pack(side="right")
        ttk.Label(self.detail, text="한글은 원본과 같은 24px 글자 칸 기준이며, 점·쉼표·영문은 폰트의 실제 폭을 사용합니다.").pack(anchor="w")
        self.load_pair()

    def preview_text(self):
        try:
            from .render_cpro import render_blueroad_at_24
            image = render_blueroad_at_24(self.ko.get("1.0", "end-1c"), int(self.advance.get()), self.project.font)
            self.after.set(image, crop=True)
            self.message("미리보기 갱신됨 · 저장 전")
        except Exception as error:
            self.error(error)

    def wrap_text(self):
        try:
            from .cpro_layout import layout_card
            lines = self.ko.get("1.0", "end-1c").splitlines()
            if len(lines) < 2:
                raise ValueError("첫 줄에 제목, 다음 줄에 본문을 입력하세요.")
            wrapped, advance = layout_card(lines[0], " ".join(lines[1:]))
            self.ko.delete("1.0", "end"); self.ko.insert("1.0", wrapped)
            self.advance.set(str(advance)); self.mark_dirty(); self.preview_text()
        except Exception as error:
            self.error(error)

    def show_image(self):
        c = self.current
        ttk.Label(self.detail, text=f"{c.get('width', '?')}×{c.get('height', '?')} · {c.get('archive') or 'PVR'}").pack(anchor="w")
        self.frame_index = tk.IntVar(value=1)
        if self.kind == "animations":
            controls = ttk.Frame(self.detail); controls.pack(fill="x", pady=5)
            ttk.Label(controls, text=f"프레임 선택 / {c['frame_count']}개").pack(side="left")
            spin = ttk.Spinbox(controls, textvariable=self.frame_index, from_=1, to=c["frame_count"], width=5,
                               command=self.frame_changed)
            spin.pack(side="left", padx=8); spin.bind("<Return>", self.frame_changed)
        self.pair()
        controls = ttk.Frame(self.detail); controls.pack(fill="x", pady=10)
        self.state = tk.StringVar(value=STATES.get(c.get("status"), "미검수"))
        state = ttk.Combobox(controls, textvariable=self.state, values=tuple(STATES[k] for k in ("unreviewed", "korean_needed", "english_keep", "no_change", "edited")), state="readonly", width=13)
        state.pack(side="left"); state.bind("<<ComboboxSelected>>", self.mark_dirty)
        ttk.Button(controls, text="수정 PNG 가져오기", command=self.import_image).pack(side="left", padx=8)
        ttk.Button(controls, text="원본 PNG 내보내기", command=self.export_image).pack(side="left")
        ttk.Button(controls, text="검수 내용 저장", command=self.save_current).pack(side="right")
        ttk.Label(self.detail, text="검수 메모").pack(anchor="w")
        self.note = self.text_widget(self.detail, 4); self.note.pack(fill="x", pady=4)
        self.note.insert("1.0", c.get("note", ""))
        if c.get("labels"):
            columns = ttk.Frame(self.detail); columns.pack(fill="x", pady=6)
            columns.columnconfigure(0, weight=1); columns.columnconfigure(1, weight=1)
            ttk.Label(columns, text="이미지 일본어 문구 (한 줄에 한 항목)").grid(row=0, column=0, sticky="w")
            ttk.Label(columns, text="한글 번역 (같은 순서)").grid(row=0, column=1, sticky="w")
            self.image_jp = self.text_widget(columns, min(9, len(c["labels"]) + 1))
            self.image_ko = self.text_widget(columns, min(9, len(c["labels"]) + 1))
            self.image_jp.grid(row=1, column=0, sticky="ew", padx=(0, 7)); self.image_ko.grid(row=1, column=1, sticky="ew")
            self.image_jp.insert("1.0", "\n".join(x["japanese"] for x in c["labels"]))
            self.image_ko.insert("1.0", "\n".join(x["korean"] for x in c["labels"]))
            hint = ("자막 이미지의 문구를 저장하면 영덕 블루로드체로 자동 렌더링합니다. 원본 영어 글리프와 장식은 유지합니다."
                    if c.get("renderer") == "stage_caption_atlas" else
                    "그림 속 문구를 바꾸면 해당 문구를 그린 수정 PNG도 가져와야 디스크에 반영됩니다.")
            ttk.Label(self.detail, text=hint).pack(anchor="w")
            if self.kind == "animations":
                sequence = ", ".join(str(label["frame"] + 1) for label in c["labels"])
                ttk.Label(self.detail, text=f"문구별 프레임 순서: {sequence} · 바꾼 문구가 있는 프레임의 PNG를 다시 가져오세요.").pack(anchor="w")
        ttk.Label(self.detail, text="CPRO 번역 카드, PVR/PVM 수정 이미지와 SAN 수정 프레임을 테스트 디스크에 적용합니다.").pack(anchor="w", pady=6)
        self.load_pair()

    def frame_changed(self, event=None):
        try:
            frame = self.frame_index.get() - 1
            if not 0 <= frame < self.current["frame_count"]:
                raise ValueError("프레임 번호를 확인하세요.")
            self.generation += 1; self.load_pair(frame)
        except Exception as error:
            self.error(error)

    def import_image(self):
        source = filedialog.askopenfilename(parent=self.window, title="수정 PNG 선택", filetypes=(("PNG 이미지", "*.png"),))
        if not source:
            return
        try:
            frame = self.frame_index.get() - 1 if self.kind == "animations" else 0
            self.project.import_image(self.kind, self.selected, source, frame)
            self.state.set("수정본 준비"); self.dirty = True; self.load_pair(frame); self.render_list()
        except Exception as error:
            self.error(error)

    def export_image(self):
        if self.before.original is None:
            return
        output = filedialog.asksaveasfilename(parent=self.window, title="원본 PNG 내보내기", defaultextension=".png",
            initialfile=self.selected.replace(":", "_") + ".png", filetypes=(("PNG 이미지", "*.png"),))
        if output:
            self.before.original.save(output, format="PNG"); self.message("원본 PNG 내보내기 완료")

    def show_media(self):
        self.segments = copy.deepcopy(self.current.get("segments", []))
        self.segment_index = None
        self.segment_fields_dirty = False
        self.loading_segments = False
        self.duration = self.current.get("duration")
        ttk.Label(self.detail, text="음성 인식 초안은 원음 청취 검수가 필요합니다. Ctrl+Space: 재생/정지").pack(anchor="w", pady=(0, 5))
        self.player = NativePlayer(self.detail, self.project.font, self.live_segments, self.error)
        self.player.pack(fill="x")
        self.timing_notice = ttk.Label(self.detail, style="Error.TLabel"); self.timing_notice.pack(anchor="w", pady=5)
        table = ttk.Frame(self.detail); table.pack(fill="x")
        columns = ("number", "start", "end", "jp", "ko", "state")
        self.segment_list = ttk.Treeview(table, columns=columns, show="headings", height=6, selectmode="browse")
        widths = (35, 65, 65, 250, 250, 90)
        for name, title, width in zip(columns, ("#", "시작", "끝", "일본어 원문", "한글 자막", "검수"), widths):
            self.segment_list.heading(name, text=title); self.segment_list.column(name, width=width, minwidth=30)
        self.segment_list.tag_configure("invalid", background="#623d49", foreground="#fff4ec")
        scrollbar = ttk.Scrollbar(table, command=self.segment_list.yview)
        self.segment_list.configure(yscrollcommand=scrollbar.set)
        self.segment_list.pack(side="left", fill="x", expand=True); scrollbar.pack(side="right", fill="y")
        self.segment_list.bind("<<TreeviewSelect>>", self.on_segment_pick)
        times = ttk.Frame(self.detail); times.pack(fill="x", pady=5)
        self.start = tk.StringVar(value="0"); self.end = tk.StringVar(value="0")
        for label, variable in (("시작", self.start), ("끝", self.end)):
            ttk.Label(times, text=label).pack(side="left")
            entry = ttk.Entry(times, textvariable=variable, width=9); entry.pack(side="left", padx=4)
            entry.bind("<KeyRelease>", self.segment_edited)
        for label, action in (("현재 시간 → 시작", lambda: self.set_time_field(self.start)),
                              ("현재 시간 → 끝", lambda: self.set_time_field(self.end)),
                              ("선택 구간으로 이동", lambda: self.player.seek(float(self.start.get())))):
            ttk.Button(times, text=label, command=action).pack(side="left", padx=3)
        texts = ttk.Frame(self.detail); texts.pack(fill="x")
        texts.columnconfigure(0, weight=1); texts.columnconfigure(1, weight=1)
        ttk.Label(texts, text="선택 구간 일본어").grid(row=0, column=0, sticky="w")
        ttk.Label(texts, text="선택 구간 한글 자막").grid(row=0, column=1, sticky="w")
        self.jp = self.text_widget(texts, 3); self.jp.grid(row=1, column=0, sticky="ew", padx=(0, 7))
        self.ko = self.text_widget(texts, 3); self.ko.grid(row=1, column=1, sticky="ew")
        self.jp.bind("<KeyRelease>", self.segment_edited); self.ko.bind("<KeyRelease>", self.segment_edited)
        actions = ttk.Frame(self.detail); actions.pack(fill="x", pady=8)
        for label, action in (("구간 적용", self.apply_segment), ("현재 시간에 구간 추가", self.add_segment), ("선택 구간 삭제", self.delete_segment)):
            ttk.Button(actions, text=label, command=action).pack(side="left", padx=(0, 5))
        ttk.Label(actions, text="검수").pack(side="left", padx=(6, 3))
        self.segment_state = tk.StringVar(value=SEGMENT_STATES["manual"])
        state = ttk.Combobox(actions, textvariable=self.segment_state, values=tuple(SEGMENT_STATES.values()), state="readonly", width=14)
        state.pack(side="left")
        state.bind("<<ComboboxSelected>>", self.segment_edited)
        ttk.Button(actions, text="자막 저장 (Ctrl+S)", command=self.save_current).pack(side="right")
        ttk.Label(self.detail, text="저장 후 ‘자막 내장 ROM 생성’으로 다시 빌드하면 게임에 반영됩니다. 영어 원문은 유지합니다.").pack(anchor="w")
        self.render_segments()
        project, kind, item_id = self.project, self.kind, self.selected
        def ready(prepared):
            self.player.load(prepared)
            self.duration = self.player.duration
            self.render_segments()
            self.message("앱 내부 재생 준비됨")
        self.async_job(lambda: project.prepare_media(kind, item_id), ready, "음성·영상 재생을 준비하는 중…")

    def live_segments(self):
        result = self.segments.copy()
        if self.segment_index is not None and self.segment_fields_dirty and self.segment_index < len(result):
            result[self.segment_index] = result[self.segment_index] | {
                "start": self.start.get(), "end": self.end.get(),
                "japanese": self.jp.get("1.0", "end-1c"), "korean": self.ko.get("1.0", "end-1c"),
                "status": self.segment_status()}
        return result

    def segment_status(self):
        reverse = {label: key for key, label in SEGMENT_STATES.items()}
        return reverse.get(self.segment_state.get(), "manual")

    def segment_edited(self, event=None):
        if not self.loading:
            self.segment_fields_dirty = True; self.mark_dirty()

    def render_segments(self, selection=None):
        self.loading_segments = True
        self.segment_list.delete(*self.segment_list.get_children())
        errors = timing_errors(self.segments, self.duration)
        for index, s in enumerate(self.segments):
            self.segment_list.insert("", "end", iid=str(index), values=(index + 1, s.get("start", ""), s.get("end", ""),
                s.get("japanese", ""), s.get("korean", ""), "시간 오류" if index in errors else SEGMENT_STATES.get(s.get("status"), "미검수")), tags=("invalid",) if index in errors else ())
        self.timing_notice.configure(text=f"시간 오류 {len(errors)}개 · 실제 길이 {self.duration:.3f}초" if errors and self.duration else (f"시간 오류 {len(errors)}개" if errors else "시간 범위 확인됨"))
        if selection is not None and self.segment_list.exists(str(selection)):
            self.segment_list.selection_set(str(selection))
        self.loading_segments = False

    def on_segment_pick(self, event=None):
        selection = self.segment_list.selection()
        if self.loading_segments or not selection:
            return
        index = int(selection[0])
        if index == self.segment_index:
            return
        if self.segment_fields_dirty and not self.apply_segment(redraw=False):
            if self.segment_index is not None:
                self.segment_list.selection_set(str(self.segment_index))
            return
        self.select_segment(index)

    def select_segment(self, index):
        self.segment_index = index
        self.loading = True
        s = self.segments[index]
        self.start.set(str(s.get("start", 0))); self.end.set(str(s.get("end", 0)))
        self.segment_state.set(SEGMENT_STATES.get(s.get("status"), "미검수"))
        for widget, field in ((self.jp, "japanese"), (self.ko, "korean")):
            widget.delete("1.0", "end"); widget.insert("1.0", s.get(field, ""))
        self.segment_fields_dirty = False
        self.loading = False

    def set_time_field(self, variable):
        if self.segment_index is not None:
            variable.set(f"{self.player.position():.3f}"); self.segment_edited()

    def apply_segment(self, redraw=True):
        if self.segment_index is None or not self.segment_fields_dirty:
            return True
        try:
            value = {"start": float(self.start.get()), "end": float(self.end.get()),
                     "japanese": self.jp.get("1.0", "end-1c"), "korean": self.ko.get("1.0", "end-1c"), "status": self.segment_status()}
            self.segments[self.segment_index] = self.segments[self.segment_index] | value
            self.segment_fields_dirty = False
            if redraw:
                self.render_segments(self.segment_index)
            return True
        except Exception as error:
            self.error(error); return False

    def add_segment(self):
        if not self.apply_segment():
            return
        start = self.player.position()
        end = min(start + 2, self.duration) if self.duration else start + 2
        if end <= start:
            self.message("클립 끝에서는 구간을 추가할 수 없습니다."); return
        self.segments.append({"start": round(start, 3), "end": round(end, 3), "japanese": "", "korean": "", "status": "manual"})
        index = len(self.segments) - 1
        self.render_segments(index); self.select_segment(index); self.mark_dirty()

    def delete_segment(self):
        if self.segment_index is None:
            return
        self.segments.pop(self.segment_index)
        self.segment_index = None; self.segment_fields_dirty = False
        self.render_segments()
        for widget in (self.jp, self.ko):
            widget.delete("1.0", "end")
        self.mark_dirty()

    def save_current(self):
        if not self.selected:
            return True
        try:
            if self.kind == "text":
                value = {"japanese": self.jp.get("1.0", "end-1c"), "korean": self.ko.get("1.0", "end-1c"),
                         "fullwidth_advance": int(self.advance.get()), "status": self.state.get()}
            elif self.kind in ("images", "animations"):
                reverse = {STATES[k]: k for k in ("unreviewed", "korean_needed", "english_keep", "no_change", "edited")}
                value = {"status": reverse[self.state.get()], "note": self.note.get("1.0", "end-1c")}
                if self.current.get("labels"):
                    jp = self.image_jp.get("1.0", "end-1c").splitlines()
                    ko = self.image_ko.get("1.0", "end-1c").splitlines()
                    labels = self.current["labels"]
                    if len(jp) != len(labels) or len(ko) != len(labels) or any(not x.strip() for x in jp + ko):
                        raise ValueError(f"원문과 번역은 각각 {len(labels)}개 항목으로 입력하세요.")
                    value["labels"] = [label | {"japanese": j.strip(), "korean": k.strip()} for label, j, k in zip(labels, jp, ko)]
            else:
                if not self.apply_segment():
                    return False
                errors = timing_errors(self.segments, self.duration)
                if errors:
                    self.render_segments()
                    raise ValueError("시간 오류를 먼저 수정하세요.\n" + "\n".join(f"{i+1}번: {reason}" for i, reason in list(errors.items())[:8]))
                value = {"segments": self.segments, "status": "in_review"}
            record = self.project.save_record(self.kind, self.selected, value, getattr(self, "duration", None))
            self.current.update(record); self.dirty = False
            self.render_list()
            if self.kind == "text":
                self.preview_text()
            self.message("저장 완료 · 이전 내용은 work/editor-backups에 보관됨")
            return True
        except Exception as error:
            self.error(error); return False

    def choose_project(self):
        if not self.leave():
            return
        path = filedialog.askdirectory(parent=self.window, title="한글화 프로젝트 폴더 선택")
        if not path:
            return
        try:
            self.project = Project(path)
            self.project_label.configure(text=str(self.project.root))
            caption_config = read_json(self.project.root / "work/runtime/config.json", {})
            selected_style = caption_config.get("caption_style", "box")
            self.caption_style.set("검은 배경" if selected_style == "box" else "검정 테두리")
            self.caption_opacity.set(str(round(caption_config.get("caption_box_alpha", 115) * 100 / 255)))
            self.switch(self.kind, force=True)
        except Exception as error:
            self.error(error)

    def choose_disc(self):
        path = filedialog.askdirectory(parent=self.window, title="원본 CUE/BIN이 있는 폴더 선택", initialdir=str(self.project.disc))
        if path:
            from .disc import GDImage
            try:
                with GDImage(Path(path)):
                    pass
                self.project.disc = Path(path)
                self.project._commit({self.project.data / "native_editor.json": json.dumps({"disc": path}, ensure_ascii=False, indent=2).encode("utf-8")})
                self.message("원본 디스크 위치 저장됨")
            except Exception as error:
                self.error(error)

    def export_csv(self):
        if not self.leave():
            return
        output = filedialog.asksaveasfilename(parent=self.window, title="번역·자막 CSV 내보내기", initialdir=str(self.project.data),
            initialfile="localization_export.csv", defaultextension=".csv", filetypes=(("CSV", "*.csv"),))
        if output:
            try:
                count = self.project.export_text(output); self.message(f"텍스트·자막 {count}행 내보내기 완료")
            except Exception as error:
                self.error(error)

    def export_runtime(self):
        if not self.leave():
            return
        try:
            from .runtime_config import export_runtime
            report = export_runtime(self.project)
            self.message(f"자막 데이터 준비 · {len(report['clips'])}개 클립, {report['cue_count']}개 구간 · ‘자막 내장 ROM 생성’으로 적용하세요.")
        except Exception as error:
            self.error(error)

    def set_caption_style(self, event=None):
        try:
            from .runtime_config import export_runtime
            opacity = float(self.caption_opacity.get())
            if not 0 <= opacity <= 100:
                raise ValueError("배경 농도는 0~100% 사이로 입력하세요.")
            path = self.project.root / "work/runtime/config.json"
            if not path.is_file():
                export_runtime(self.project)
            config = read_json(path, {})
            config["caption_style"] = "box" if self.caption_style.get() == "검은 배경" else "outline"
            config["caption_box_alpha"] = round(opacity * 255 / 100)
            self.project._commit({path: (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")})
            self.message(f"자막 배경 농도 {opacity:g}% 저장 · ROM을 다시 생성하면 반영됩니다.")
        except Exception as error:
            self.error(error)

    def launch_player(self):
        if not self.leave():
            return
        try:
            from .runtime_launcher import launch_player
            result = launch_player(self.project)
            self.message(f"자막 포함 게임 실행 · 저장한 한글 자막 {result['cue_count']}구간 적용")
        except Exception as error:
            self.error(error)

    def build_disc(self):
        if not self.leave():
            return
        output = self.project.root / "work/poc/Track5_KR.bin"
        env = os.environ.copy(); env["SC5_PROJECT_ROOT"] = str(self.project.root); env["PYTHONUTF8"] = "1"
        args = [sys.executable]
        if getattr(sys, "frozen", False):
            args += ["--build-disc", "--project", str(self.project.root)]
        else:
            args += ["-m", "sc5.native_editor", "--build-disc", "--project", str(self.project.root)]
        args += ["--disc", str(self.project.disc), "--output", str(output)]
        def build():
            result = subprocess.run(args, cwd=str(self.project.root), env=env, capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                worker_error = self.project.root / "work/native-worker-error.json"
                detail = json.loads(worker_error.read_text(encoding="utf-8")).get("error", "") if worker_error.exists() else ""
                raise RuntimeError(detail[-2000:] or result.stderr.decode("utf-8", "replace")[-2000:] or "테스트 디스크 생성 실패")
            report = self.project.root / "work/native-disc-build.json"
            return json.loads(report.read_text(encoding="utf-8"))
        self.async_job(build, lambda report: self.message(f"ROM 내장 자막 {report['native']['stats']['cues']}개 · 생성 완료: {report['package']['chd']}"),
                       "텍스트·이미지·자막을 ROM에 넣고 CHD/GDI를 생성하는 중…", guard=False)

    def close(self, force=False):
        if not force and not self.leave():
            return
        self.closed = True
        self.window.after_cancel(self._pump_timer)
        if self.player:
            self.player.destroy(); self.player = None
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=project_root())
    parser.add_argument("--disc", type=Path)
    parser.add_argument("--build-disc", action="store_true")
    parser.add_argument("--package-native-rom", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--smoke-section", choices=("full", "caption_review", "san_review"), default="full")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    os.environ["SC5_PROJECT_ROOT"] = str(args.project.resolve())
    if args.package_native_rom:
        from .native_subtitles import package_rom
        package_rom()
        return
    if args.build_disc:
        from .build_text import build
        project = Project(args.project, args.disc)
        result = build(project.disc, args.output or project.root / "work/poc/Track5_KR.bin")
        from .runtime_config import export_runtime
        from .native_subtitles import build as build_native, package_rom
        export_runtime(project)
        result['native'] = build_native()
        result['package'] = package_rom()
        (project.root / "work/native-disc-build.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if args.smoke_test:
        from .native_smoke import run, run_caption_review
        if args.smoke_section == "san_review":
            from .san_smoke import run_san_review
            smoke = run_san_review
        else:
            smoke = run_caption_review if args.smoke_section == "caption_review" else run
        report = smoke(args.project, args.disc)
        output = args.report or args.project / "work/native-editor-smoke.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not report.get("success"):
            raise SystemExit(1)
        return
    root = tk.Tk()
    try:
        path = args.project
        if not (path / "data/edits.json").exists():
            root.withdraw()
            chosen = filedialog.askdirectory(parent=root, title="data/edits.json이 있는 프로젝트 폴더 선택")
            if not chosen:
                root.destroy(); return
            path = Path(chosen); root.deiconify()
        Editor(root, Project(path, args.disc))
        root.mainloop()
    except Exception as error:
        messagebox.showerror("편집기 실행 오류", str(error), parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
