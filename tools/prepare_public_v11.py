"""Stage v1.1 from the verified final local disc; never modify original tracks."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PUBLIC=Path('C:/CODEX/DC-Space-Channel-5-Kr')
RELEASE=Path('E:/CodexBuilds/SC5-v1.1/release')
PATCH=RELEASE/'DC-Space-Channel-5-Kr-v1.1-Patch'
ORIGINAL=Path('C:/CODEX/roms/DC/Space Channel 5 (Japan)')
TARGET=ROOT/'output/native-rom-movie-dialogue-fixed'
OLD=ROOT/'work/github-v0.85/DC-Space-Channel-5-Kr-v0.85-Patch'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def write(path,value):
    text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    for base,label in ((ROOT,'<PROJECT>'),(PUBLIC,'<PUBLIC>'),(ORIGINAL,'<ORIGINAL>'),(RELEASE.parent,'<RELEASE_WORK>')):
        for prefix in (str(base),str(base).replace('\\','/')):
            text=text.replace(json.dumps(prefix)[1:-1],label)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,'utf-8')

def copy(relative):
    dest=PUBLIC/relative;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,dest)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    (PATCH/'patches').mkdir(parents=True,exist_ok=True)
    shutil.copytree(OLD/'bin',PATCH/'bin',dirs_exist_ok=True)
    for path in (ROOT/'sc5').glob('*.py'):copy(path.relative_to(ROOT))
    for path in (PUBLIC/'native').glob('*'):
        if (ROOT/'native'/path.name).is_file():copy(path.relative_to(PUBLIC))
    for name in ('build_native_editor.py','build_native_subtitles.py','release_patcher.py','prepare_public_v11.py',
                 'verify_movie_revision.py','verify_profile_revision.py','rebuild_profile_cards.py','align_movie_dialogue.py','apply_movie_assets.py'):
        copy(Path('tools')/name)
    for path in (PUBLIC/'data').rglob('*'):
        relative=path.relative_to(PUBLIC)
        if path.is_file() and (ROOT/relative).is_file() and path.name not in ('disc.json','localization_progress.json','localization_export.csv'):
            if path.suffix=='.json':write(path,json.loads((ROOT/relative).read_text('utf-8')))
            else:copy(relative)
    for path in (PUBLIC/'assets').rglob('*'):
        relative=path.relative_to(PUBLIC)
        if path.is_file() and (ROOT/relative).is_file():copy(relative)
    shutil.copy2(ROOT/'data/text_export.csv',PUBLIC/'data/localization_export.csv')
    movie=json.loads((ROOT/'data/movie_replacements.json').read_text('utf-8'))
    from sc5.disc import GDImage
    with GDImage(ORIGINAL) as disc:
        entries={e.name:e for e in disc.entries()}
        for row in movie['movies']:
            entry=entries[row['name']];raw=disc.read(entry.lba,entry.size)
            assert hashlib.sha256(raw).hexdigest()==row['original_sha256']
            source=RELEASE/(row['name']+'.original');source.write_bytes(raw)
            delta=PUBLIC/'assets/movie-edits'/(row['name']+'.xdelta');delta.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run([str(PATCH/'bin/xdelta3.exe'),'-9','-e','-s',str(source),str(ROOT/row['path']),str(delta)],check=True)
            source.unlink()
            row.update(patch=delta.relative_to(PUBLIC).as_posix(),patch_sha256=sha(delta),
                       patch_tool='bin/xdelta3.exe',patch_tool_sha256=sha(PATCH/'bin/xdelta3.exe'))
    write(PUBLIC/'data/movie_replacements.json',movie)
    (PUBLIC/'run_workbench.cmd').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0SC5KoreanWorkbench_v16.exe" --project "%~dp0."\r\n')
    progress=json.loads((PUBLIC/'data/localization_progress.json').read_text('utf-8'))
    progress.update(release='v1.1',release_type='stable unofficial Korean localization',
                    native_editor='SC5KoreanWorkbench_v16.exe',
                    native_editor_status='Latest profile, HUD and movie source; movie delta restored from user original',
                    latest_batch='v1.1 results HUD, profile text/layout and movie dialogue corrections')
    write(PUBLIC/'data/localization_progress.json',progress)
    for name,relative in {
        'results-hud-v11.json':'data/latest_results_hud_review.json',
        'profile-text-v11.json':'data/latest_profile_text_review.json',
        'movie-dialogue-v11.json':'data/latest_movie_dialogue_review.json',
        'load-ui-original-comparison.json':'work/load-ui-review-20261008/texture-comparison.json',
    }.items():write(PUBLIC/'docs/verification'/name,json.loads((ROOT/relative).read_text('utf-8')))
    pictures={
        '20-results-v11.png':'results-hud-review-20261008/results-fixed.png',
        '21-profile-body-v11.png':'profile-text-review-20261008/body-after.png',
        '22-profile-dancing-v11.png':'profile-text-review-20261008/dancing.png',
        '23-profile-morolians-v11.png':'profile-text-review-20261008/morolians.png',
        '24-profile-musicians-v11.png':'profile-text-review-20261008/musicians.png',
        '25-profile-earth-v11.png':'profile-text-review-20261008/earth.png',
        '26-movie-dialogue-v11.png':'movie-dialogue-review-20261008/movie-dialogue-fixed.png',
    }
    evidence=json.loads((PUBLIC/'docs/verification/screenshots.json').read_text('utf-8'))
    for name,source in pictures.items():
        path=ROOT/'work'/source;shutil.copy2(path,PUBLIC/'docs/screenshots'/name)
        evidence['screenshots'].append({'file':name,'sha256':sha(path),'kind':'native_rom_capture',
            'captured_version':'post-v0.85 correction included in v1.1','source':source,
            'stock_core_unmodified':True,'movie_test_note':'Interlude playback test uses a test-only scene filename redirect; final disc restored' if 'movie-' in name else None})
    manifest=json.loads((OLD/'manifest.json').read_text('utf-8'))
    manifest.update(version='v1.1',editor='SC5KoreanWorkbench_v16.exe',release_type='stable',
        latest_fixes=['results HUD texture state','profile white strokes and centered categories','R4 movie dialogue and caption position'])
    for track in manifest['tracks']:
        original=ORIGINAL/track['source_name'];target=TARGET/track['output_name']
        assert sha(original)==track['source_sha256']
        track.update(output_size=target.stat().st_size,output_sha256=sha(target))
        if track.get('patch'):
            subprocess.run([str(PATCH/'bin/xdelta3.exe'),'-9','-e','-s',str(original),str(target),str(PATCH/track['patch'])],check=True)
            track['patch_sha256']=sha(PATCH/track['patch'])
        print('Verified track',track['number'],flush=True)
    chd=ROOT/'output/Space Channel 5 Korean Movie Dialogue Fixed.chd'
    assert sha(chd)=='1f582b3705deb7ce1411f1e98eb846e0927d687a556dba9455154feb49373ae8'
    manifest.update(chd_size=chd.stat().st_size,chd_sha256=sha(chd),gdi_text=(TARGET/'Space Channel 5 Korean Native.gdi').read_text('ascii'))
    write(PATCH/'manifest.json',manifest);write(PUBLIC/'docs/original-and-output-hashes.json',manifest)
    evidence.update(version='v1.1',chd_sha256=sha(chd));write(PUBLIC/'docs/verification/screenshots.json',evidence)
    shutil.copy2(ROOT/'tools/release_patcher.py',PATCH/'release_patcher.py')
    print('Prepared',PATCH,flush=True)

if __name__=='__main__':main()
