"""Verify the packaged ROM with the official libretro core and frontend APIs.

Only standard controller and screenshot UDP messages are sent. No core RAM
writes, subtitle overlays, custom emulator binary, or Lua drawing is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import time
import threading
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/native-rom/stock-libretro'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, default=240)
parser.add_argument('--title-only', action='store_true', help='Capture the title screen without starting a game')
parser.add_argument('--rom', type=Path, default=ROOT/'output/Space Channel 5 Korean Native.chd')
parser.add_argument('--cpu', action='store_true', help='Enter the original CPU cheat through standard RetroPad inputs')
parser.add_argument('--cpu-at', type=int, default=125)
parser.add_argument('--skip-opening-at', type=int, default=90)
parser.add_argument('--instruction-review', action='store_true', help='Capture first control instruction and short voice reply every 0.25 seconds')
parser.add_argument('--run-name', help='Keep this run in a separate evidence folder')
parser.add_argument('--record', type=Path, help='Record game audio and video through the standard frontend recorder')
parser.add_argument('--save-state-at',type=int,default=0,help='Save a standard frontend state for read-only ROM diagnostic inspection')
args = parser.parse_args()
run_name = args.run_name or datetime.now().strftime('%Y%m%d-%H%M%S')
if not run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in run_name):
    parser.error('--run-name must contain only letters, numbers, hyphens and underscores')
RUN = OUT/'runs'/run_name
RUN.mkdir(parents=True, exist_ok=False)
SCREENS = RUN/'screenshots'
SCREENS.mkdir()
exe = Path(r'C:\CODEX\tools\RetroArch-1.22.2\RetroArch-Win64\retroarch.exe')
cfg = RUN/'retroarch-test.cfg'
text = (OUT/'retroarch-test.cfg').read_text('utf-8')
text = '\n'.join(line for line in text.splitlines() if not line.startswith('screenshot_directory'))
text += f'\nscreenshot_directory = "{SCREENS}"\nvideo_font_enable = "false"\nhistory_list_enable = "false"\n'
cfg.write_text(text,'utf-8')
command = [str(exe), '-v', '--log-file', str(RUN/'stock-chd.log'), '-c', str(cfg),
           '-L', str(OUT/'flycast_libretro.dll'), str(args.rom.resolve())]
if args.record:
    recording_config=RUN/'recording-test.cfg'
    recording_config.write_text('vcodec = "libx264rgb"\nacodec = "flac"\nformat = "matroska"\nthreads = "2"\nvideo_preset = "ultrafast"\nvideo_crf = "0"\n', 'ascii')
    command += ['--record', str(args.record.resolve()), '--recordconfig', str(recording_config), '--size=640x480']
info = subprocess.STARTUPINFO()
info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
info.wShowWindow = 0
process = subprocess.Popen(command, cwd=OUT, startupinfo=info,
    creationflags=subprocess.CREATE_NO_WINDOW, stdout=(RUN/'stock-chd-stdout.log').open('w'), stderr=subprocess.STDOUT)
proof = {'pid':process.pid,'command':command, 'actions':[],
         'retroarch_sha256':hashlib.file_digest(exe.open('rb'),'sha256').hexdigest(),
         'core_sha256':hashlib.file_digest((OUT/'flycast_libretro.dll').open('rb'),'sha256').hexdigest(),
         'rom_sha256':hashlib.file_digest(args.rom.open('rb'),'sha256').hexdigest(),
         'host_subtitle_code':False,'core_memory_writes':False,
         'run_directory':str(RUN), 'capture_times':[], 'capture_requests':[]}
sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
def button(identifier, down):
    sock.sendto(struct.pack('<iiiiH2x',0,1,0,identifier,down),('127.0.0.1',55438))
def action(name, value=None):
    proof['actions'].append({'seconds':round(time.monotonic()-start,3),'action':name,'value':value})
    (RUN/'stock-chd-proof.json').write_text(json.dumps(proof,indent=2),'utf-8')
    print(name,value,flush=True)
def capture():
    elapsed=round(time.monotonic()-start,3)
    proof['capture_requests'].append({'seconds':elapsed})
    sock.sendto(b'SCREENSHOT\n',('127.0.0.1',55437))
    action('SCREENSHOT request')

capture_stop=threading.Event()
def preserve_completed_captures():
    # Standard frontend screenshots finish asynchronously and have names with
    # only second precision. Preserve completed files on a separate thread.
    # Request times and PNG completion times are reported separately.
    from PIL import Image
    while not capture_stop.is_set():
        for path in SCREENS.glob('*.png'):
            if path.name.startswith('frame-'):
                continue
            try:
                stamp=path.stat().st_mtime_ns
                with Image.open(path) as im:
                    im.verify()
                target=SCREENS/f'frame-{stamp}.png'
                path.rename(target)
            except (OSError,ValueError,SyntaxError):
                continue
            proof['capture_times'].append({
                'completed_seconds':round(time.monotonic()-start,3),
                'png_mtime_ns':stamp,'path':str(target)})
        capture_stop.wait(.01)
start=time.monotonic()
capture_worker=threading.Thread(target=preserve_completed_captures,daemon=True)
capture_worker.start()
cpu_entered=False
state_saved=False
(RUN/'stock-chd-proof.json').write_text(json.dumps(proof,indent=2),'utf-8')
try:
    schedule=[] if args.title_only else [(40,'START',3),(43,'A',0)]
    if args.skip_opening_at and not args.title_only:
        schedule.append((args.skip_opening_at,'Skip opening via START',3))
    captures=list(range(20,args.seconds,4)) if args.title_only else list(range(55,86,3))+list(range(105,args.seconds,4))
    if args.instruction_review:
        captures=sorted(set(captures + [125 + index*.25 for index in range(241)]))
    while time.monotonic()-start < args.seconds:
        if process.poll() is not None:raise RuntimeError(f'Official frontend exited: {process.returncode}')
        elapsed=time.monotonic()-start
        if schedule and elapsed>=schedule[0][0]:
            _,name,identifier=schedule.pop(0)
            button(identifier,1);time.sleep(.3);button(identifier,0);action(name)
        if captures and elapsed>=captures[0]:
            captures.pop(0);capture()
        if args.cpu and elapsed>=args.cpu_at and not cpu_entered:
            button(12,1);button(13,1);time.sleep(.2)
            for identifier in [4,6,0,6,0,5,7,8,7,8]:
                button(identifier,1);time.sleep(.15);button(identifier,0);time.sleep(.12)
            button(12,0);button(13,0);cpu_entered=True;action('CPU cheat controller sequence')
        if args.save_state_at and elapsed>=args.save_state_at and not state_saved:
            sock.sendto(b'SAVE_STATE\n',('127.0.0.1',55437));state_saved=True;action('SAVE_STATE')
        time.sleep(.025 if args.instruction_review else .1)
finally:
    button(0,0);button(3,0)
    sock.sendto(b'QUIT\n',('127.0.0.1',55437))
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=8)
    time.sleep(.1)
    capture_stop.set();capture_worker.join(timeout=2)
    proof['exit_code']=process.returncode
    proof['screenshots']=[str(p) for p in sorted(SCREENS.glob('*.png'))]
    (RUN/'stock-chd-proof.json').write_text(json.dumps(proof,indent=2),'utf-8')
    (OUT/'stock-chd-proof.json').write_text(json.dumps(proof,indent=2),'utf-8')
