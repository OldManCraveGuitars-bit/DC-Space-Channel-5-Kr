"""Verify v1.1 packaged installer and movie reconstruction, then make ZIPs."""
import csv,json,re,shutil,sys,types,zipfile
from pathlib import Path
from prepare_public_v11 import ROOT,PUBLIC,RELEASE,PATCH,ORIGINAL,sha,write

def normalized(code):
    return code.replace(co_filename='<source>',co_consts=tuple(
        normalized(c) if isinstance(c,types.CodeType) else c for c in code.co_consts))

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    proof=json.loads((RELEASE.parent/'patch-roundtrip/patch-result.json').read_text('utf-8'))
    manifest=json.loads((PATCH/'manifest.json').read_text('utf-8'))
    assert proof['success'] and proof['chd_sha256']==manifest['chd_sha256']
    for actual,expected in zip(proof['tracks'],manifest['tracks'],strict=True):
        assert actual['sha256']==expected['output_sha256']
        assert sha(ORIGINAL/expected['source_name'])==expected['source_sha256']
    proof.update(patcher_exe_sha256=sha(PATCH/'SC5KoreanPatcher_v1.1.exe'),
        test_method='Packaged Windows executable, original JP five BINs, complete GDI/CHD generation',
        original_hashes_rechecked_after_apply=True)
    write(PUBLIC/'docs/verification/patch-roundtrip.json',proof)
    for name in ('prepare_public_v11.py','finalize_public_v11.py'):shutil.copy2(ROOT/'tools'/name,PUBLIC/'tools'/name)
    editor=RELEASE.parent/'SC5KoreanWorkbench_v16.exe'
    from PyInstaller.archive.readers import CArchiveReader
    archive=CArchiveReader(str(editor));pyz=archive.open_embedded_archive('PYZ.pyz')
    modules=('sc5.movie_assets','sc5.build_text','sc5.editor_project','sc5.render_cpro','sc5.profile_layout','sc5.native_subtitles','sc5.native_smoke')
    for module in modules:
        path=ROOT/Path(module.replace('.','/')+'.py')
        assert normalized(pyz.extract(module))==normalized(compile(path.read_text('utf-8'),str(path),'exec')),module
    bundle=RELEASE/'DC-Space-Channel-5-Kr-v1.1-Workbench'
    bundle.mkdir(exist_ok=False)
    for folder in ('assets','data','native','sc5','tools','docs'):
        shutil.copytree(PUBLIC/folder,bundle/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (bundle/'bin').mkdir();shutil.copy2(PATCH/'bin/xdelta3.exe',bundle/'bin/xdelta3.exe')
    shutil.copy2(editor,bundle/editor.name)
    from sc5.editor_project import Project
    namespace={'__name__':'sc5.movie_assets'};exec(pyz.extract('sc5.movie_assets'),namespace)
    project=Project(bundle,ORIGINAL)
    paths,rows=namespace['registered_movies'](project)
    for row in rows:
        assert sha(paths[row['name']])==row['sha256']
        assert not (bundle/row['path']).exists()
    second,_=namespace['registered_movies'](project)
    assert paths==second
    editor_proof={'version':'v1.1','exe':editor.name,'size':editor.stat().st_size,'sha256':sha(editor),
        'bundled_modules_match_source':list(modules),'movie_delta_reconstructed_from_original':True,
        'movie_reconstructed_sha256':{name:sha(path) for name,path in paths.items()},
        'movie_cache_reuse_verified':True,'full_clean_environment_ROM_rebuild_tested':False}
    write(PUBLIC/'docs/verification/editor-v16-bundle.json',editor_proof)
    shutil.copy2(PUBLIC/'docs/verification/editor-v16-bundle.json',bundle/'docs/verification/editor-v16-bundle.json')
    # Only a verification cache created by this script is removed. Its resolved
    # path must be inside this release bundle; no source or user files are moved.
    cache=(bundle/'work').resolve()
    assert cache.is_relative_to(bundle.resolve()) and cache.name=='work'
    shutil.rmtree(cache)
    for name in ('README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(PUBLIC/name,PATCH/name);shutil.copy2(PUBLIC/name,bundle/name)
    for name in ('requirements.txt','run_workbench.cmd'):shutil.copy2(PUBLIC/name,bundle/name)
    shutil.copytree(PUBLIC/'docs',PATCH/'docs')
    assert editor.name in (bundle/'run_workbench.cmd').read_text('ascii')
    with (PUBLIC/'data/localization_export.csv').open(encoding='utf-8-sig',newline='') as stream:
        assert len(list(csv.DictReader(stream)))==861
    forbidden={'.bin','.chd','.gdi','.cue','.afs','.sfd','.m1v','.state','.mp4','.wav'}
    for directory in (PATCH,bundle):
        assert not [p for p in directory.rglob('*') if p.is_file() and p.suffix.lower() in forbidden]
    for file in (PUBLIC/'README.md',PUBLIC/'CHANGELOG.md',PUBLIC/'docs/DEVELOPMENT.md',PUBLIC/'THIRD_PARTY_NOTICES.md'):
        for link in re.findall(r'\]\(([^)]+)\)',file.read_text('utf-8')):
            if not link.startswith(('http:','https:','#')):
                assert (file.parent/link.split('#')[0]).exists(),(file,link)
    outputs=[]
    for directory in (PATCH,bundle):
        target=RELEASE/(directory.name+'.zip')
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for path in sorted(directory.rglob('*')):
                if path.is_file():z.write(path,Path(directory.name)/path.relative_to(directory))
        with zipfile.ZipFile(target) as z:assert z.testzip() is None
        outputs.append(target);print('Archived',target.name,flush=True)
    csv_path=RELEASE/'DC-Space-Channel-5-Kr-v1.1-Text.csv'
    shutil.copy2(PUBLIC/'data/localization_export.csv',csv_path);outputs.append(csv_path)
    sums=RELEASE/'SHA256SUMS.txt';sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in outputs),'ascii')
    report={'version':'v1.1','ready':True,'release_type':'stable','chd_sha256':manifest['chd_sha256'],
        'installer_roundtrip_passed':True,'movie_delta_reconstruction_passed':True,
        'editor_sha256':sha(editor),'physical_console_tested':False,
        'files':[{'name':p.name,'size':p.stat().st_size,'sha256':sha(p)} for p in outputs+[sums]]}
    write(RELEASE/'publication.json',report);print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
