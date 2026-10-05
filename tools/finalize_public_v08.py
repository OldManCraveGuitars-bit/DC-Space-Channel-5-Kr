"""Verify the packaged patcher result, then assemble the v0.8 release."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT))
from prepare_public_v08 import PUBLIC,RELEASE,PATCH,ORIGINAL,sha,write_json

def archive(folder,target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file():z.write(path,Path(folder.name)/path.relative_to(folder))
    with zipfile.ZipFile(target) as z:assert z.testzip() is None

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    proof=json.loads((RELEASE/'patch-roundtrip/patch-result.json').read_text('utf-8'))
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    assert proof['success'] and proof['chd_sha256']==manifest['chd_sha256']
    assert len(proof['tracks'])==5
    for item,track in zip(proof['tracks'],manifest['tracks']):
        assert item['sha256']==track['output_sha256']
        assert sha(ORIGINAL/track['source_name'])==track['source_sha256']
    proof.update(patcher_exe_sha256=sha(PATCH/'SC5KoreanPatcher_v0.8.exe'),
                 test_method='Packaged v0.8 Windows executable CLI, original five BIN tracks, complete GDI/CHD generation',
                 original_hashes_rechecked_after_apply=True)
    write_json(PUBLIC/'docs/verification/patch-roundtrip.json',proof)
    from finalize_public_v07 import licenses_and_project
    licenses_and_project()
    for name in ('prepare_public_v08.py','document_public_v08.py','finalize_public_v08.py'):
        shutil.copy2(ROOT/'tools'/name,PUBLIC/'tools'/name)
    editor=ROOT/'SC5KoreanWorkbench_v8.exe'
    readme=PUBLIC/'README.md';text=readme.read_text('utf-8')
    old_manifest=json.loads((ROOT/'work/github-v0.7/DC-Space-Channel-5-Kr-v0.7-Patch/manifest.json').read_text('utf-8'))
    replacements={old_manifest['chd_sha256']:manifest['chd_sha256'],
                  old_manifest['tracks'][4]['output_sha256']:manifest['tracks'][4]['output_sha256'],
                  '11145912c0f7842e17a3e4f8282e95673feeed52a5177b42be24d2156d9f78de':sha(editor),
                  'Workbench v6 `.exe`':'Workbench v8 `.exe`',
                  '별도 결과 해시 검증 기록으로 제공합니다.':'별도 결과 해시 검증 기록으로 제공합니다. v0.8 배포 실행 파일을 사용한 실제 적용 결과는 원본 5개 트랙과 최종 CHD 해시 검사를 통과했습니다.',
                  '일치하는지 확인합니다. 근거는':'일치하는지 확인했습니다. 근거는'}
    for old,new in replacements.items():text=text.replace(old,new)
    assert text.startswith('![스페이스 채널 5 한글 메인 화면]')
    readme.write_text(text,'utf-8')
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md'):shutil.copy2(PUBLIC/name,PATCH/name)
    shutil.copytree(PUBLIC/'docs',PATCH/'docs',dirs_exist_ok=True)
    shutil.copy2(PUBLIC/'data/localization_export.csv',PATCH/'DC-Space-Channel-5-Kr-v0.8-Text.csv')
    bundle=RELEASE/'DC-Space-Channel-5-Kr-v0.8-Workbench';bundle.mkdir(exist_ok=False)
    for folder in ('assets','data','native','sc5','tools','docs'):
        shutil.copytree(PUBLIC/folder,bundle/folder)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md','requirements.txt','run_workbench.cmd'):
        shutil.copy2(PUBLIC/name,bundle/name)
    shutil.copy2(editor,bundle/editor.name)
    files=[]
    for folder in (PATCH,bundle):
        target=RELEASE/(folder.name+'.zip');archive(folder,target);files.append(target)
    csv=RELEASE/'DC-Space-Channel-5-Kr-v0.8-Text.csv';shutil.copy2(PUBLIC/'data/localization_export.csv',csv);files.append(csv)
    sums=RELEASE/'SHA256SUMS.txt';sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),'ascii')
    base='https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr'
    notes=text.replace('](docs/screenshots/','](https://raw.githubusercontent.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/v0.8/docs/screenshots/')
    notes=re.sub(r'\]\((docs/[^)]+|CHANGELOG\.md|THIRD_PARTY_NOTICES\.md)\)',lambda m:']('+base+'/blob/v0.8/'+m[1]+')',notes)
    (RELEASE/'release-notes.md').write_text(notes,'utf-8')
    report={'success':True,'repo':base,'tag':'v0.8','chd_sha256':manifest['chd_sha256'],
            'packaged_patcher_roundtrip':True,'original_files_preserved':True,
            'files':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in files+[sums]]}
    write_json(RELEASE/'publication.json',report)
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
