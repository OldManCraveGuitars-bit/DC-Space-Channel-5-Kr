"""Complete release documentation, license notices and archives after QA."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = Path(r'C:\CODEX\DC-Space-Channel-5-Kr')
RELEASE = ROOT / 'work/github-v0.7'
PATCH = RELEASE / 'DC-Space-Channel-5-Kr-v0.7-Patch'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def licenses_and_project():
    from sc5.editor_project import Project
    project = Project(ROOT)
    for key, record in project.edits('animations').items():
        if record.get('status') != 'edited':
            continue
        item = project.item('animations', key)
        for frame in range(item['frame_count']):
            source = project.replacement('animations', key, frame)
            if source.is_file():
                dest = PUBLIC / source.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
    for name in ('prepare_public_v07.py', 'finalize_public_v07.py', 'release_patcher.py'):
        shutil.copyfile(ROOT / 'tools' / name, PUBLIC / 'tools' / name)
    license_root = PUBLIC / 'docs/licenses/runtime'
    license_root.mkdir(parents=True, exist_ok=True)
    packages = []
    for name in ('Pillow', 'numpy', 'fonttools', 'av', 'imageio-ffmpeg', 'PyInstaller'):
        dist = metadata.distribution(name)
        packages.append({'name': name, 'version': dist.version,
                         'project_urls': dist.metadata.get_all('Project-URL', []),
                         'pypi': f'https://pypi.org/project/{name}/{dist.version}/'})
        for entry in dist.files or []:
            if any(word in entry.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(entry))
                if source.is_file() and source.stat().st_size < 2_000_000:
                    # Include license files, not test source with license in its name.
                    if source.suffix.lower() not in ('.py', '.pyc', '.so', '.pyd'):
                        dest = license_root / name / str(entry)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, dest)
    shutil.copyfile(Path(sys.base_prefix) / 'LICENSE.txt', license_root / 'Python-LICENSE.txt')
    packages.append({'name': 'Python', 'version': sys.version.split()[0], 'source': 'https://www.python.org/downloads/source/'})
    for name in ('tcl8.6', 'tk8.6'):
        for source in (Path(sys.base_prefix) / 'tcl' / name).rglob('*'):
            if source.is_file() and 'license' in source.name.lower():
                dest = license_root / name / source.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
    (PUBLIC / 'docs/licenses/runtime-packages.json').write_text(json.dumps(packages, indent=2) + '\n', 'utf-8')
    # Credit texture preview is a production asset, not evidence of final-ROM ending playback.
    shutil.copyfile(ROOT / 'assets/image-edits/ROLL.PVM_008.png', PUBLIC / 'docs/screenshots/10-ending-credit-atlas.png')


def archive(folder, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                z.write(path, Path(folder.name) / path.relative_to(folder))


def main():
    licenses_and_project()
    proof_file = RELEASE / 'patch-roundtrip/patch-result.json'
    proof = json.loads(proof_file.read_text('utf-8'))
    manifest = json.loads((PATCH / 'manifest.json').read_text('utf-8'))
    assert proof['success'] and proof['chd_sha256'] == manifest['chd_sha256']
    assert len(proof['tracks']) == 5
    for track, expected in zip(proof['tracks'], manifest['tracks']):
        assert track['sha256'] == expected['output_sha256']
    proof.update(patcher_exe_sha256=sha(PATCH / 'SC5KoreanPatcher_v0.7.exe'),
                 test_method='Packaged Windows executable CLI, original five BIN tracks, full GDI/CHD generation',
                 original_hashes_rechecked_after_apply=False)
    # Verify that patching preserved every source track, including audio pregaps.
    original = Path(r'C:\CODEX\roms\DC\Space Channel 5 (Japan)')
    for track in manifest['tracks']:
        assert sha(original / track['source_name']) == track['source_sha256']
    proof['original_hashes_rechecked_after_apply'] = True
    (PUBLIC / 'docs/verification/patch-roundtrip.json').write_text(json.dumps(proof, indent=2) + '\n', 'utf-8')
    for name in ('README.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copyfile(PUBLIC / name, PATCH / name)
    shutil.copytree(PUBLIC / 'docs', PATCH / 'docs', dirs_exist_ok=True)
    shutil.copyfile(PUBLIC / 'data/localization_export.csv', PATCH / 'DC-Space-Channel-5-Kr-v0.7-Text.csv')
    bundle = RELEASE / 'DC-Space-Channel-5-Kr-v0.7-Workbench'
    bundle.mkdir(exist_ok=True)
    for folder in ('assets', 'data', 'native', 'sc5', 'tools', 'docs'):
        shutil.copytree(PUBLIC / folder, bundle / folder, dirs_exist_ok=True)
    for name in ('README.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md', 'requirements.txt'):
        shutil.copyfile(PUBLIC / name, bundle / name)
    shutil.copyfile(ROOT / 'SC5KoreanWorkbench_v6.exe', bundle / 'SC5KoreanWorkbench_v6.exe')
    (bundle / 'run_workbench.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0SC5KoreanWorkbench_v6.exe"\r\n', 'ascii')
    files = []
    for folder in (PATCH, bundle):
        target = RELEASE / (folder.name + '.zip')
        archive(folder, target)
        with zipfile.ZipFile(target) as z:
            assert z.testzip() is None
        files.append(target)
    csv = RELEASE / 'DC-Space-Channel-5-Kr-v0.7-Text.csv'
    shutil.copyfile(PUBLIC / 'data/localization_export.csv', csv)
    files.append(csv)
    sums = RELEASE / 'SHA256SUMS.txt'
    sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files), 'ascii')
    readme = (PUBLIC / 'README.md').read_text('utf-8')
    base = 'https://github.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr'
    readme = readme.replace('](docs/screenshots/', f'](https://raw.githubusercontent.com/OldManCraveGuitars-bit/DC-Space-Channel-5-Kr/v0.7/docs/screenshots/')
    import re
    readme = re.sub(r'\]\((docs/[^)]+|CHANGELOG\.md|THIRD_PARTY_NOTICES\.md)\)', lambda m: '](' + base + '/blob/v0.7/' + m[1] + ')', readme)
    (RELEASE / 'release-notes.md').write_text(readme, 'utf-8')
    report = {'success': True, 'repo_stage': str(PUBLIC), 'release_tag': 'v0.7',
              'files': [{'name': p.name, 'size': p.stat().st_size, 'sha256': sha(p)} for p in files + [sums]],
              'native_chd_sha256': manifest['chd_sha256'], 'packaged_patcher_roundtrip': True}
    (RELEASE / 'publication.json').write_text(json.dumps(report, indent=2) + '\n', 'utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    main()
