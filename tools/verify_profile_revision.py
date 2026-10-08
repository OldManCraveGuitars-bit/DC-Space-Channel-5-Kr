"""Verify the profile-only disc changes and the shipped editor's build code."""
from pathlib import Path
import hashlib
import json
import sys
import types

import numpy as np
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc5.cli import DEFAULT_DISC
from sc5.disc import GDImage, SECTOR, PAYLOAD
from sc5.sector import verify_mode1


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def normalize(code):
    return code.replace(co_filename='<source>', co_consts=tuple(
        normalize(value) if isinstance(value, types.CodeType) else value
        for value in code.co_consts))


def main():
    evidence = ROOT/'work/profile-text-review-20261008'
    before = ROOT/'output/native-rom-results-fixed'
    after = ROOT/'output/native-rom-profile-fixed'
    unchanged_tracks = []
    for i in range(1, 5):
        name = f'track{i:02d}.bin'
        assert digest(before/name) == digest(after/name), name
        unchanged_tracks.append(name)
    with GDImage(DEFAULT_DISC, track3=before/'track03.bin', track5=before/'track05.bin') as old, \
         GDImage(DEFAULT_DISC, track3=after/'track03.bin', track5=after/'track05.bin') as new:
        old_entries = {e.name: e for e in old.entries()}
        entries = {e.name: e for e in new.entries()}
        assert set(old_entries) == set(entries)
        assert all((old_entries[n].lba, old_entries[n].size) == (e.lba, e.size)
                   for n, e in entries.items())
        allowed = np.zeros((after/'track05.bin').stat().st_size // SECTOR, dtype=bool)
        cards = []
        with (after/'track05.bin').open('rb') as stream:
            for name, entry in entries.items():
                if name != '1ST_READ.BIN' and not name.startswith('CPRO'):
                    continue
                first = entry.lba - new.track5_start
                count = (entry.size + PAYLOAD - 1) // PAYLOAD
                allowed[first:first+count] = True
                expected = (ROOT/'work/native-rom/build/1ST_READ.BIN' if name == '1ST_READ.BIN'
                            else ROOT/'assets/pvr-edits'/name).read_bytes()
                assert new.read(entry.lba, entry.size) == expected, name
                stream.seek(first * SECTOR)
                for sector in range(count):
                    assert verify_mode1(stream.read(SECTOR)), (name, sector)
                if name.startswith('CPRO'):
                    cards.append({'name': name, 'sha256': hashlib.sha256(expected).hexdigest(),
                                  'size': entry.size, 'valid_edc_ecc_sectors': count})
        assert len(cards) == 79
    old_map = np.memmap(before/'track05.bin', dtype=np.uint8, mode='r').reshape(-1, SECTOR)
    new_map = np.memmap(after/'track05.bin', dtype=np.uint8, mode='r').reshape(-1, SECTOR)
    changed = []
    for start in range(0, len(old_map), 4096):
        indices = np.flatnonzero(np.any(old_map[start:start+4096] != new_map[start:start+4096], axis=1)) + start
        assert np.all(allowed[indices]), ('Unexpected changed sector', indices[~allowed[indices]])
        changed.extend(indices.tolist())
    archive = CArchiveReader(str(ROOT/'SC5KoreanWorkbench_v14.exe'))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    embedded = []
    for module in ('sc5.render_cpro', 'sc5.profile_layout', 'sc5.native_subtitles'):
        source = ROOT/(module.replace('.', '/')+'.py')
        expected = compile(source.read_text('utf-8'), '<source>', 'exec')
        actual = pyz.extract(module)
        assert normalize(expected) == normalize(actual), module
        embedded.append(module)
    native_key = next(key for key in archive.toc if key.replace('\\', '/') == 'native/hud.c')
    assert archive.extract(native_key) == (ROOT/'native/hud.c').read_bytes()
    report = {'passed': True, 'unchanged_tracks': unchanged_tracks,
              'all_file_sizes_and_lbas_unchanged': True,
              'changed_track5_sectors': len(changed),
              'changes_limited_to': ['1ST_READ.BIN', 'CPRO01.PVR through CPRO79.PVR'],
              'profile_cards': cards, 'editor_embedded_modules_match': embedded,
              'editor_native_hud_matches': True,
              'editor_sha256': digest(ROOT/'SC5KoreanWorkbench_v14.exe'),
              'track5_sha256': digest(after/'track05.bin')}
    (evidence/'disc-and-editor-validation.json').write_text(json.dumps(report, indent=2)+'\n', 'utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'profile_cards'}, indent=2))


if __name__ == '__main__':
    main()
