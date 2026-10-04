"""Stage the v0.7 public repository and a source-dependent delta release."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = Path(r'C:\CODEX\DC-Space-Channel-5-Kr')
RELEASE = ROOT / 'work/github-v0.7'
PATCH = RELEASE / 'DC-Space-Channel-5-Kr-v0.7-Patch'
ORIGINAL = Path(r'C:\CODEX\roms\DC\Space Channel 5 (Japan)')
XDELTA = Path(r'C:\CODEX\tools\xdelta3-v3.2.1\xdelta3-3.2.1-windows-x86_64\xdelta3.exe')
MAME = ROOT / 'work/native-rom/toolchain/mame/chdman.exe'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy(relative):
    source = ROOT / relative
    dest = PUBLIC / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=45) as response:
        path.write_bytes(response.read())


def main():
    assert not PUBLIC.exists(), 'Do not replace an existing public checkout'
    PUBLIC.mkdir()
    RELEASE.mkdir(parents=True, exist_ok=True)
    PATCH.mkdir()
    (PATCH / 'bin').mkdir()
    (PATCH / 'patches').mkdir()
    for path in (ROOT / 'sc5').glob('*.py'):
        copy(path.relative_to(ROOT))
    for name in ('native_entry.py', 'build_native_editor.py', 'build_native_subtitles.py',
                 'verify_native_rom.py', 'verify_stock_native.py', 'release_patcher.py', 'prepare_public_v07.py'):
        copy(Path('tools') / name)
    for name in ('subtitles.c', 'link.ld', 'sector_retime.c', 'sector_retime.dll'):
        copy(Path('native') / name)
    data_names = ('disc.json', 'edits.json', 'images.json', 'media.json', 'animations.json',
                  'text_review.jsonl', 'font_policy.json', 'localization_export.csv',
                  'translation_guidelines.md', 'image_text_review.jsonl', 'stage_caption_review.jsonl',
                  'animation_text_review.jsonl', 'movie_caption_review.jsonl', 'voice_caption_review.jsonl',
                  'voice225_first_line_review_20261004.json')
    for name in data_names:
        copy(Path('data') / name)
    for folder in ('translations', 'asr', 'asr-refined'):
        for path in (ROOT / 'data' / folder).rglob('*'):
            if path.is_file() and path.suffix in ('.txt', '.jsonl', '.json', '.csv'):
                copy(path.relative_to(ROOT))
    manifest = json.loads((PUBLIC / 'data/disc.json').read_text('utf-8'))
    manifest['source'] = 'SELECT_ORIGINAL_DISC_FOLDER'
    manifest['tracks'] = {'track3': 'Space Channel 5 (Japan) (Track 3).bin', 'track5': 'Space Channel 5 (Japan) (Track 5).bin'}
    (PUBLIC / 'data/disc.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    from sc5.editor_project import Project
    project = Project(ROOT)
    for key, record in project.edits('images').items():
        if record.get('status') == 'edited':
            path = project.replacement('images', key)
            assert path.is_file(), path
            copy(path.relative_to(ROOT))
        basis = record.get('stable_packing_basis', {})
        for name in ('png', 'pvr'):
            if basis.get(name):
                copy(Path(basis[name]))
    for key, record in project.edits('animations').items():
        if record.get('status') == 'edited':
            item = project.item('animations', key)
            for frame in range(item['frame_count']):
                path = project.replacement('animations', key, frame)
                if path.is_file():
                    copy(path.relative_to(ROOT))
    copy(Path('assets/image-edits/COMMON_DATA.PVM_114_2.png'))
    copy(Path('assets/fonts/yeongdeok-blueroad/Yeongdeok-Blueroad.ttf'))
    (PUBLIC / 'requirements.txt').write_text('Pillow\nnumpy\nfonttools\nav\nimageio-ffmpeg\n', 'ascii')
    (PUBLIC / '.gitignore').write_text('work/\noutput/\n.deps/\n__pycache__/\n*.pyc\n*.exe\n*.chd\n*.bin\n*.cue\n*.gdi\n*.afs\n*.pvm\n*.zip\n', 'ascii')
    (PUBLIC / '.gitattributes').write_text('*.py text eol=lf\n*.md text eol=lf\n*.json text eol=lf\n*.jsonl text eol=lf\n*.csv binary\n*.png binary\n*.ttf binary\n*.pvr binary\n*.dll binary\n', 'ascii')
    (PUBLIC / 'docs/screenshots').mkdir(parents=True)
    screenshots = {
        '01-title.png': 'work/native-rom/stock-libretro/runs/v07-title-20261005/screenshots/frame-1791142707521452600.png',
        '02-greeting.png': 'work/native-rom/stock-libretro/runs/atlas-uncompressed-20261005/screenshots/frame-1791141848447460100.png',
        '03-spoken-instruction.png': 'work/native-rom/stock-libretro/runs/atlas-uncompressed-20261005/screenshots/frame-1791141895435482100.png',
        '04-gameplay-hud.png': 'work/native-rom/stock-libretro/runs/atlas-uncompressed-20261005/screenshots/frame-1791141891069195500.png',
        '05-cpu-gameplay.png': 'work/native-rom/stock-libretro/runs/atlas-uncompressed-20261005/screenshots/frame-1791141960127719000.png',
        '06-texture-quality.png': 'work/atlas-vq-quality-20261005/comparison.png',
        '07-text-card-comparison.png': 'work/cpro76-79_comparison.png',
        '08-image-atlas.png': 'assets/image-edits/COMMON_DATA.PVM_114_2.png',
        '09-character-categories.png': 'assets/image-edits/TITLE.PVM_090.png',
    }
    evidence = {'version': 'v0.7', 'chd_sha256': sha(ROOT / 'output/Space Channel 5 Korean Native.chd'), 'screenshots': []}
    for name, relative in screenshots.items():
        source = ROOT / relative
        assert source.is_file(), source
        shutil.copyfile(source, PUBLIC / 'docs/screenshots' / name)
        evidence['screenshots'].append({'file': name, 'sha256': sha(source), 'kind': 'current_native_rom_capture' if name[:2] in ('01','02','03','04','05') else 'asset_preview_or_comparison', 'source': relative})
    (PUBLIC / 'docs/verification').mkdir()
    for name, relative in {
        'native-disc.json': 'work/native-rom/package-disc-validation.json',
        'texture.json': 'work/atlas-vq-quality-20261005/texture-validation.json',
        'gameplay-observations.json': 'work/atlas-vq-quality-20261005/visual-observations.json',
        'stock-title.json': 'work/native-rom/stock-libretro/runs/v07-title-20261005/stock-chd-proof.json',
        'stock-gameplay.json': 'work/native-rom/stock-libretro/runs/atlas-uncompressed-20261005/stock-chd-proof.json',
    }.items():
        content = (ROOT / relative).read_text('utf-8')
        content = content.replace(str(ROOT).replace('\\', '\\\\'), '<PROJECT>').replace(str(ROOT), '<PROJECT>')
        (PUBLIC / 'docs/verification' / name).write_text(content, 'utf-8')
    (PUBLIC / 'docs/verification/screenshots.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    licenses = PUBLIC / 'docs/licenses'
    download('https://raw.githubusercontent.com/jmacd/xdelta/v3.2.1/xdelta3/LICENSE', licenses / 'xdelta3-Apache-2.0.txt')
    download('https://raw.githubusercontent.com/mamedev/mame/mame0289/COPYING', licenses / 'MAME-COPYING.txt')
    download('https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt', licenses / 'GPL-2.0.txt')
    shutil.copyfile(XDELTA, PATCH / 'bin/xdelta3.exe')
    shutil.copyfile(MAME, PATCH / 'bin/chdman.exe')
    tracks = []
    for number in range(1, 6):
        source = next(ORIGINAL.glob(f'*Track {number}).bin'))
        target = ROOT / 'output/native-rom' / f'track{number:02d}.bin'
        tracks.append({'number': number, 'source_name': source.name, 'source_size': source.stat().st_size,
                       'source_sha256': sha(source), 'output_name': target.name, 'output_size': target.stat().st_size,
                       'output_sha256': sha(target), 'skip_source_bytes': 150 * 2352 if number in (2,4) else 0})
    def encode(track):
        if track['number'] not in (3,5):
            return
        source = ORIGINAL / track['source_name']
        target = ROOT / 'output/native-rom' / track['output_name']
        relative = f"patches/track{track['number']:02d}.xdelta"
        command = [str(XDELTA), '-9', '-e', '-s', str(source), str(target), str(PATCH / relative)]
        subprocess.run(command, check=True)
        track.update(patch=relative, patch_sha256=sha(PATCH / relative))
        print(json.dumps({'encoded': relative, 'size': (PATCH / relative).stat().st_size}), flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(encode, tracks))
    gdi = ROOT / 'output/native-rom/Space Channel 5 Korean Native.gdi'
    chd = ROOT / 'output/Space Channel 5 Korean Native.chd'
    manifest = {'version': 'v0.7', 'game': 'Space Channel 5 (Japan)', 'tracks': tracks,
                'gdi_name': gdi.name, 'gdi_text': gdi.read_text('ascii'), 'chd_name': chd.name,
                'chd_size': chd.stat().st_size, 'chd_sha256': sha(chd), 'subtitles_embedded': True,
                'external_subtitle_files_required': False, 'tools': [
                    {'file': 'bin/xdelta3.exe', 'version': '3.2.1', 'sha256': sha(XDELTA)},
                    {'file': 'bin/chdman.exe', 'version': 'MAME 0.289', 'sha256': sha(MAME)}]}
    (PATCH / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    (PUBLIC / 'docs/original-and-output-hashes.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    shutil.copyfile(ROOT / 'tools/release_patcher.py', PATCH / 'release_patcher.py')
    print(json.dumps({'public': str(PUBLIC), 'patch_folder': str(PATCH), 'source_files': len(list(PUBLIC.rglob('*')))}), flush=True)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    main()
