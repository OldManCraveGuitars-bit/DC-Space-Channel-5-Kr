"""Stage v0.8 against the existing clean v0.7 public repository."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=Path(r'C:\CODEX\DC-Space-Channel-5-Kr')
RELEASE=ROOT/'work/github-v0.8'
PATCH=RELEASE/'DC-Space-Channel-5-Kr-v0.8-Patch'
OLD=ROOT/'work/github-v0.7/DC-Space-Channel-5-Kr-v0.7-Patch'
ORIGINAL=Path(r'C:\CODEX\roms\DC\Space Channel 5 (Japan)')

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def copy(relative):
    source=ROOT/relative;dest=PUBLIC/relative
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,str):
        for prefix in (str(ROOT),str(ROOT).replace('\\','/'),str(PUBLIC),str(ORIGINAL)):
            value=value.replace(prefix,'<PROJECT>' if prefix!=str(ORIGINAL) else '<ORIGINAL>')
        return value
    return value

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    RELEASE.mkdir(exist_ok=False)
    (PATCH/'patches').mkdir(parents=True)
    shutil.copytree(OLD/'bin',PATCH/'bin')
    for path in (ROOT/'sc5').glob('*.py'):copy(path.relative_to(ROOT))
    for name in ('judgment.c','subtitles.c','link.ld','sector_retime.c','sector_retime.dll'):copy(Path('native')/name)
    for name in ('build_native_editor.py','build_native_subtitles.py','native_entry.py','verify_native_rom.py','release_patcher.py','prepare_public_v08.py'):
        copy(Path('tools')/name)
    for name in ('judgment_artwork.json','judgment_progress.json','judgment_png_application_review_20261006.json'):
        write_json(PUBLIC/'data'/name,json.loads((ROOT/'data'/name).read_text('utf-8')))
    for name in ('SET_JUDGMENT.png','SET_JUDGMENT_2.png'):copy(Path('assets/image-edits')/name)
    copy(Path('run_workbench.cmd'))
    screenshots={'11-judgment-default.png':'approved-revision-options-default.png',
                 '12-judgment-level2.png':'approved-revision-level2.png',
                 '13-judgment-level6.png':'approved-revision-level6.png',
                 '14-main-menu-v08.png':'approved-revision-title.png'}
    evidence=json.loads((PUBLIC/'docs/verification/screenshots.json').read_text('utf-8'))
    for record in evidence['screenshots']:
        record['captured_version']='v0.7'
        if record['kind']=='current_native_rom_capture':record['kind']='previous_native_rom_capture'
    for name,source_name in screenshots.items():
        source=ROOT/'work/judgment/stock/screenshots'/source_name
        shutil.copy2(source,PUBLIC/'docs/screenshots'/name)
        evidence['screenshots'].append({'file':name,'sha256':sha(source),'kind':'current_native_rom_capture',
                                      'captured_version':'v0.8','source':'work/judgment/stock/screenshots/'+source_name})
    shutil.copy2(ROOT/'assets/image-edits/SET_JUDGMENT_2.png',PUBLIC/'docs/screenshots/15-judgment-user-png.png')
    evidence['screenshots'].append({'file':'15-judgment-user-png.png','sha256':sha(ROOT/'assets/image-edits/SET_JUDGMENT_2.png'),
                                  'kind':'user_approved_asset','captured_version':'v0.8'})
    evidence.update(version='v0.8',chd_sha256=sha(ROOT/'output/Space Channel 5 Korean Native.chd'))
    write_json(PUBLIC/'docs/verification/screenshots.json',evidence)
    sources={'native-disc.json':'work/native-rom/package-disc-validation.json',
             'judgment-artwork.json':'work/native-rom/build/judgment-art-report.json',
             'judgment-boundaries.json':'work/judgment/boundaries/results.json',
             'judgment-adjacent-notes.json':'work/judgment/boundaries/overlap-results.json',
             'judgment-stock-core.json':'work/judgment/stock/proof.json',
             'judgment-user-png.json':'data/judgment_png_application_review_20261006.json',
             'editor-v8-bundle.json':'work/judgment/editor-v8-bundle-proof.json'}
    for name,relative in sources.items():
        value=json.loads((ROOT/relative).read_text('utf-8'))
        if name in ('judgment-boundaries.json','judgment-adjacent-notes.json'):
            value['scope']='Mechanics verified before the final PNG update; only artwork changed afterwards.'
        write_json(PUBLIC/'docs/verification'/name,value)
    manifest=json.loads((OLD/'manifest.json').read_text('utf-8'))
    manifest['version']='v0.8'
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
                              'default':1,'cold_boot_resets_to_default':True,'unselected_alpha':128},
                    editor='SC5KoreanWorkbench_v8.exe')
    for tool in manifest['tools']:assert sha(PATCH/tool['file'])==tool['sha256']
    write_json(PATCH/'manifest.json',manifest)
    write_json(PUBLIC/'docs/original-and-output-hashes.json',manifest)
    shutil.copy2(ROOT/'tools/release_patcher.py',PATCH/'release_patcher.py')
    print(json.dumps({'staged':str(PATCH),'chd_sha256':manifest['chd_sha256']}),flush=True)

if __name__=='__main__':main()
