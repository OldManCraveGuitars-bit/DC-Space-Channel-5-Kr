"""Validate packaged v0.85 application and assemble the public archives."""
import json,shutil,sys
from pathlib import Path
from prepare_public_v085 import ROOT,PUBLIC,RELEASE,PATCH,ORIGINAL,sha,write_json
from finalize_public_v08 import archive


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    proof=json.loads((RELEASE/'patch-roundtrip/patch-result.json').read_text('utf-8'))
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    assert proof['success'] and proof['chd_sha256']==manifest['chd_sha256']
    assert len(proof['tracks'])==5
    for result,expected in zip(proof['tracks'],manifest['tracks']):
        assert result['sha256']==expected['output_sha256']
        assert sha(ORIGINAL/expected['source_name'])==expected['source_sha256']
    proof.update(patcher_exe_sha256=sha(PATCH/'SC5KoreanPatcher_v0.85.exe'),
        test_method='Packaged v0.85 Windows executable CLI, original JP five BIN tracks, complete GDI/CHD generation',
        original_hashes_rechecked_after_apply=True)
    write_json(PUBLIC/'docs/verification/patch-roundtrip.json',proof)
    from finalize_public_v07 import licenses_and_project
    licenses_and_project()
    for name in ('prepare_public_v085.py','document_public_v085.py','finalize_public_v085.py'):
        shutil.copy2(ROOT/'tools'/name,PUBLIC/'tools'/name)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(PUBLIC/name,PATCH/name)
    shutil.copytree(PUBLIC/'docs',PATCH/'docs')
    shutil.copy2(PUBLIC/'data/localization_export.csv',PATCH/'DC-Space-Channel-5-Kr-v0.85-Text.csv')
    bundle=RELEASE/'DC-Space-Channel-5-Kr-v0.85-Workbench';bundle.mkdir(exist_ok=False)
    ignore=shutil.ignore_patterns('__pycache__','*.pyc')
    for folder in ('assets','data','native','sc5','tools','docs'):
        shutil.copytree(PUBLIC/folder,bundle/folder,ignore=ignore)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md','requirements.txt','run_workbench.cmd'):
        shutil.copy2(PUBLIC/name,bundle/name)
    editor=ROOT/'SC5KoreanWorkbench_v12.exe';shutil.copy2(editor,bundle/editor.name)
    assert 'SC5KoreanWorkbench_v12.exe' in (bundle/'run_workbench.cmd').read_text('ascii')
    assert (bundle/'native/hud.c').read_bytes()==(ROOT/'native/hud.c').read_bytes()
    for directory in (PATCH,bundle):
        forbidden=[p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in {'.bin','.chd','.gdi','.cue','.afs','.state','.mp4','.wav'}]
        assert not forbidden,forbidden
    files=[]
    for directory in (PATCH,bundle):
        target=RELEASE/(directory.name+'.zip');archive(directory,target);files.append(target)
    csv=RELEASE/'DC-Space-Channel-5-Kr-v0.85-Text.csv'
    shutil.copy2(PUBLIC/'data/localization_export.csv',csv);files.append(csv)
    sums=RELEASE/'SHA256SUMS.txt';sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),'ascii')
    report={'success':True,'repo':'https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr',
        'tag':'v0.85','chd_sha256':manifest['chd_sha256'],'packaged_patcher_roundtrip':True,
        'new_screenshots':4,'main_screenshot_at_top':True,'physical_console_tested':False,
        'files':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in files+[sums]]}
    write_json(RELEASE/'publication.json',report)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
