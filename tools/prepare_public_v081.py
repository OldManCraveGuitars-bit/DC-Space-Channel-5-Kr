"""Stage v0.81 native VMU persistence against the published v0.8 project."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from prepare_public_v08 import ROOT,PUBLIC,ORIGINAL,sha,copy,write_json

RELEASE=ROOT/'work/github-v0.81'
PATCH=RELEASE/'DC-Space-Channel-5-Kr-v0.81-Patch'
OLD=ROOT/'work/github-v0.8/DC-Space-Channel-5-Kr-v0.8-Patch'

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    validation=json.loads((ROOT/'work/judgment/v081-stock/vmu-validation.json').read_text('utf-8'))
    assert validation['passed']
    RELEASE.mkdir(exist_ok=False)
    (PATCH/'patches').mkdir(parents=True)
    shutil.copytree(OLD/'bin',PATCH/'bin')
    for path in (ROOT/'sc5').glob('*.py'):copy(path.relative_to(ROOT))
    for name in ('judgment.c','judgment_vmu.c','subtitles.c','link.ld','sector_retime.c','sector_retime.dll'):
        copy(Path('native')/name)
    for name in ('build_native_editor.py','build_native_subtitles.py','native_entry.py','verify_native_rom.py',
                 'release_patcher.py','prepare_public_v081.py','document_public_v081.py','finalize_public_v081.py'):
        copy(Path('tools')/name)
    for name in ('judgment_artwork.json','judgment_progress.json'):
        write_json(PUBLIC/'data'/name,json.loads((ROOT/'data'/name).read_text('utf-8')))
    progress_path=PUBLIC/'data/localization_progress.json'
    progress=json.loads(progress_path.read_text('utf-8')) if progress_path.exists() else {}
    progress.update(judgment_option=json.loads((ROOT/'data/judgment_progress.json').read_text('utf-8')),
                    native_editor='SC5KoreanWorkbench_v9.exe',
                    native_editor_status='v9 includes native VMU setting persistence and latest approved PNG',
                    latest_batch='v0.81 native judgment VMU persistence and revised user PNG')
    write_json(PUBLIC/'data/localization_progress.json',progress)
    copy(Path('assets/image-edits/SET_JUDGMENT_2.png'))
    copy(Path('run_workbench.cmd'))
    for name,relative in {
        'native-disc.json':'work/native-rom/package-disc-validation.json',
        'judgment-artwork.json':'work/native-rom/build/judgment-art-report.json',
        'judgment-vmu.json':'work/judgment/v081-stock/vmu-validation.json',
        'editor-v9-bundle.json':'work/judgment/editor-v9-bundle-proof.json',
    }.items():write_json(PUBLIC/'docs/verification'/name,json.loads((ROOT/relative).read_text('utf-8')))
    # Keep all existing screenshot bytes and their captured-version labels.
    manifest=json.loads((OLD/'manifest.json').read_text('utf-8'));manifest['version']='v0.81'
    for track in manifest['tracks']:
        original=ORIGINAL/track['source_name'];target=ROOT/'output/native-rom'/track['output_name']
        assert sha(original)==track['source_sha256']
        checksum=sha(target)
        if track['number']==3:
            assert checksum==track['output_sha256'];shutil.copy2(OLD/track['patch'],PATCH/track['patch'])
        track.update(output_size=target.stat().st_size,output_sha256=checksum)
        if track['number']==5:
            subprocess.run([str(PATCH/'bin/xdelta3.exe'),'-9','-e','-s',str(original),str(target),str(PATCH/track['patch'])],check=True)
            track['patch_sha256']=sha(PATCH/track['patch'])
            print(json.dumps({'encoded':track['patch'],'bytes':(PATCH/track['patch']).stat().st_size}),flush=True)
    chd=ROOT/'output/Space Channel 5 Korean Native.chd'
    manifest.update(chd_size=chd.stat().st_size,chd_sha256=sha(chd),
                    gdi_text=(ROOT/'output/native-rom/Space Channel 5 Korean Native.gdi').read_text('ascii'),
                    judgment={'levels':[1,2,3,4,5,6],'added_seconds':[0,.02,.04,.06,.08,.1],
                              'default_without_saved_setting':1,'cold_boot_resets_to_default':False,
                              'VMU_setting_persistence':True,'setting_filename':'SC5KR_JUDGE',
                              'VMU_blocks':2,'save_settle_frames':90,'unselected_alpha':128,
                              'original_Japanese_progress_save_format_changed':False},
                    editor='SC5KoreanWorkbench_v9.exe')
    for tool in manifest['tools']:assert sha(PATCH/tool['file'])==tool['sha256']
    write_json(PATCH/'manifest.json',manifest)
    write_json(PUBLIC/'docs/original-and-output-hashes.json',manifest)
    shutil.copy2(ROOT/'tools/release_patcher.py',PATCH/'release_patcher.py')
    print(json.dumps({'staged':str(PATCH),'chd_sha256':manifest['chd_sha256']}),flush=True)

if __name__=='__main__':main()
