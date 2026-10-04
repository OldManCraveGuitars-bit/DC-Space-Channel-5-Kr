"""Windows patch installer for the original five-track Japanese dump."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading

BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def apply(source, output, *, make_chd=True, log=lambda message: None, package=None):
    package = Path(package or BASE).resolve()
    manifest = json.loads((package / 'manifest.json').read_text('utf-8'))
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.is_file():
        source = source.parent
    if not source.is_dir():
        raise ValueError('원본 CUE/BIN 또는 GDI 폴더를 선택하세요.')
    if output == source or output in source.parents:
        raise ValueError('원본 폴더와 다른 새 출력 폴더를 선택하세요.')
    if output.exists():
        raise ValueError('출력 폴더가 이미 있습니다. 새 폴더 이름을 지정하세요.')
    candidates = list(source.glob('*.bin'))
    sources, known = {}, {}
    for track in manifest['tracks']:
        log(f"원본 트랙 {track['number']} 확인 중…")
        matching = [p for p in candidates if p.stat().st_size == track['source_size']]
        found = None
        for path in matching:
            known.setdefault(path, sha(path))
            if known[path] == track['source_sha256']:
                found = path
                break
        if found is None:
            raise ValueError(f"트랙 {track['number']}의 크기/SHA-256이 대상 일본판과 다릅니다. README의 원본 해시를 확인하세요.")
        sources[track['number']] = found
    for record in manifest['tools']:
        if sha(package / record['file']) != record['sha256']:
            raise ValueError('패치 도구 파일이 손상되었습니다. ZIP을 다시 받아 주세요.')
    for track in manifest['tracks']:
        if track.get('patch') and sha(package / track['patch']) != track['patch_sha256']:
            raise ValueError('패치 파일이 손상되었습니다. ZIP을 다시 받아 주세요.')
    output.parent.mkdir(parents=True, exist_ok=True)
    required = sum(t['output_size'] for t in manifest['tracks']) + (manifest['chd_size'] if make_chd else 0) + 64_000_000
    if shutil.disk_usage(output.parent).free < required:
        raise ValueError('출력 드라이브의 여유 공간이 부족합니다. 최소 3GB를 확보하세요.')
    output.mkdir()
    proof = {'version': manifest['version'], 'success': False, 'tracks': [], 'original_files_modified': False}

    def run(command):
        result = subprocess.run([str(v) for v in command], capture_output=True,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            detail = (result.stdout + result.stderr).decode('utf-8', 'replace')[-1800:]
            raise RuntimeError(detail or '패치 도구 실행 실패')
        return (result.stdout + result.stderr).decode('utf-8', 'replace')

    try:
        for track in manifest['tracks']:
            dest = output / track['output_name']
            original = sources[track['number']]
            log(f"트랙 {track['number']} 생성 중…")
            if track.get('patch'):
                run([package / 'bin/xdelta3.exe', '-d', '-s', original, package / track['patch'], dest])
            else:
                with original.open('rb') as reader, dest.open('wb') as writer:
                    reader.seek(track.get('skip_source_bytes', 0))
                    shutil.copyfileobj(reader, writer)
            checksum = sha(dest)
            if dest.stat().st_size != track['output_size'] or checksum != track['output_sha256']:
                raise RuntimeError(f"트랙 {track['number']} 결과 검증 실패")
            proof['tracks'].append({'number': track['number'], 'sha256': checksum, 'size': dest.stat().st_size})
        gdi = output / manifest['gdi_name']
        gdi.write_text(manifest['gdi_text'], 'ascii')
        proof['gdi_sha256'] = sha(gdi)
        if make_chd:
            log('검증된 GDI를 CHD로 변환 중…')
            chd = output / manifest['chd_name']
            run([package / 'bin/chdman.exe', 'createcd', '-i', gdi, '-o', chd, '-np', '8'])
            log('CHD 무결성 확인 중…')
            proof['chd_integrity'] = run([package / 'bin/chdman.exe', 'verify', '-i', chd])
            proof['chd_sha256'] = sha(chd)
            if proof['chd_sha256'] != manifest['chd_sha256']:
                raise RuntimeError('CHD SHA-256이 배포 기준 빌드와 다릅니다.')
        proof['success'] = True
        log(f'완료: {output}')
        return proof
    finally:
        # Keep partial output for diagnosis; never overwrite or delete original files.
        (output / 'patch-result.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), 'utf-8')


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root = tk.Tk()
    root.title('Space Channel 5 한국어 패치 v0.7')
    root.geometry('690x350')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Space Channel 5 일본판 → 한국어 v0.7', font=('맑은 고딕', 14)).pack(anchor='w')
    ttk.Label(frame, text='원본 5트랙 CUE/BIN 폴더를 선택하면 GDI와 CHD를 생성합니다.').pack(anchor='w', pady=(6, 18))
    source = tk.StringVar()
    output = tk.StringVar(value=str(Path.home() / 'Space Channel 5 Korean v0.7'))
    chd = tk.BooleanVar(value=True)
    for label, variable, title in [('원본 폴더', source, '일본판 원본 BIN 폴더 선택'), ('출력 폴더', output, '출력할 상위 폴더 선택')]:
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=6)
        ttk.Label(row, text=label, width=10).pack(side='left')
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        def choose(v=variable, t=title):
            picked = filedialog.askdirectory(parent=root, title=t)
            if picked:
                v.set(str(Path(picked) / 'Space Channel 5 Korean v0.7') if v is output else picked)
        ttk.Button(row, text='선택', command=choose).pack(side='left', padx=(7, 0))
    ttk.Checkbutton(frame, text='CHD도 생성 (GDI와 5개 BIN은 항상 생성)', variable=chd).pack(anchor='w', pady=8)
    status = tk.StringVar(value='대상 원본의 크기와 SHA-256을 검사합니다. 여유 공간 3GB 이상 필요.')
    ttk.Label(frame, textvariable=status, wraplength=645).pack(anchor='w', pady=8)
    progress = ttk.Progressbar(frame, mode='indeterminate')
    progress.pack(fill='x', pady=6)
    events = queue.Queue()
    busy = False

    def start():
        nonlocal busy
        if not source.get():
            messagebox.showerror('원본 선택', '원본 폴더를 선택하세요.', parent=root)
            return
        busy = True
        button.configure(state='disabled')
        progress.start()
        # Read Tk variables on the UI thread only.
        chosen_source, chosen_output, chosen_chd = source.get(), output.get(), chd.get()
        def worker():
            try:
                apply(chosen_source, chosen_output, make_chd=chosen_chd, log=lambda s: events.put(('log', s)))
                events.put(('done', chosen_output))
            except Exception as error:
                events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    button = ttk.Button(frame, text='한국어 패치 적용', command=start)
    button.pack(anchor='e', pady=6)
    def pump():
        nonlocal busy
        try:
            while True:
                kind, text = events.get_nowait()
                status.set(text)
                if kind in ('done', 'error'):
                    busy = False
                    progress.stop()
                    button.configure(state='normal')
                    if kind == 'done':
                        messagebox.showinfo('패치 완료', f'GDI/CHD 생성과 해시 검증을 완료했습니다.\n{text}', parent=root)
                    else:
                        messagebox.showerror('패치 중단', text, parent=root)
        except queue.Empty:
            pass
        root.after(100, pump)
    def close():
        if busy:
            messagebox.showinfo('패치 적용 중', '파일 생성이 완료된 뒤 닫아 주세요.', parent=root)
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(100, pump)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--no-chd', action='store_true')
    args = parser.parse_args()
    if args.source or args.output:
        if not (args.source and args.output):
            parser.error('--source and --output are both required')
        try:
            apply(args.source, args.output, make_chd=not args.no_chd, package=args.package)
        except Exception:
            # Windowed executables have no stderr; save the actual CLI error.
            error_file = Path(args.package or BASE) / 'patch-error.txt'
            import traceback
            error_file.write_text(traceback.format_exc(), 'utf-8')
            raise SystemExit(1)
    else:
        gui()


if __name__ == '__main__':
    main()
