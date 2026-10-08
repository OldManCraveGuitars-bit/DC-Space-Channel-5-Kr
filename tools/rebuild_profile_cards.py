"""Rebuild only CPRO cards in the current localized filesystem, preserving its LBAs."""
from pathlib import Path
import hashlib
import json
import os
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc5.assets import encode_vq_like, decode_pvr
from sc5.disc import GDImage
from sc5.editor_project import Project
from sc5.patch_disc import patch
from sc5.render_cpro import render_blueroad_at_24


def main():
    project = Project(ROOT)
    folder = ROOT / 'work/profile-text-review-20261008'
    track = ROOT / 'work/poc/Track5_KR.bin'
    pending = track.with_name(f'Track5_KR.profile-building-{os.getpid()}.bin')
    paths, cards = {}, []
    by, bx = np.indices((256, 256), dtype=np.uint32)
    morton = np.zeros((256, 256), dtype=np.uint32)
    for bit in range(8):
        morton |= ((by >> bit) & 1) << (bit * 2)
        morton |= ((bx >> bit) & 1) << (bit * 2 + 1)
    with GDImage(project.disc, track3=ROOT/'work/poc/Track3_KR.bin', track5=track) as disc:
        entries = {e.name: e for e in disc.entries()}
        for name, record in sorted(project.edits('text').items()):
            if not name.startswith('CPRO') or record.get('status') == '영어 유지':
                continue
            text = (project.data/'translations'/(name[:-4]+'.txt')).read_text('utf-8').strip()
            assert text == record['korean']
            rendered = render_blueroad_at_24(text, record.get('fullwidth_advance', 26), project.font)
            entry = entries[name]
            previous = disc.read(entry.lba, entry.size)
            packed = encode_vq_like(previous, rendered)
            p = packed.index(b'PVRT')
            assert packed[:p+16] == previous[:p+16] and len(packed) == len(previous)
            assert packed[p+8:p+10] == bytes([2, 3])
            table = np.frombuffer(packed, '<u2', 1024, p+16).reshape(256, 4)
            indices = np.frombuffer(packed, np.uint8, 65536, p+16+2048)
            blocks = table[indices[morton]]
            actual = np.empty((512, 512), dtype=np.uint16)
            for dx, dy, index in [(0,0,0), (0,1,1), (1,0,2), (1,1,3)]:
                actual[dy::2, dx::2] = blocks[:, :, index]
            alpha = np.asarray(rendered.getchannel('A'), dtype=np.uint16)
            assert np.array_equal(actual, ((alpha // 17) << 12) | 0x0fff)
            if name in {'CPRO06.PVR', 'CPRO56.PVR', 'CPRO79.PVR'}:
                assert decode_pvr(packed).tobytes() == rendered.tobytes()
            path = ROOT/'assets/pvr-edits'/name
            path.write_bytes(packed)
            rendered.save(ROOT/'assets/image-edits'/(name+'.png'))
            paths[name] = path
            cards.append({'name': name, 'lba': entry.lba, 'size': entry.size,
                          'fullwidth_advance': record.get('fullwidth_advance', 26),
                          'pvr_sha256': hashlib.sha256(packed).hexdigest(),
                          'roundtrip_exact': True, 'bounds': rendered.getchannel('A').getbbox()})
        try:
            count = patch(disc, paths, pending)
        except BaseException:
            pending.unlink(missing_ok=True)
            raise
    pending.replace(track)
    report = {'cards': cards, 'patched_sectors': count, 'profile_body_scale': [1, 1],
              'profile_body_line_spacing': 23, 'other_file_data_and_LBAs_unchanged': True}
    (folder/'profile-card-build.json').write_text(json.dumps(report, indent=2)+'\n', 'utf-8')
    manifest_path = ROOT/'work/poc/text_build.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    updated = {c['name']: c for c in cards}
    manifest['cards'] = [c | updated[c['name']] for c in manifest['cards']]
    manifest['profile_rasterization'] = json.loads((project.data/'font_policy.json').read_text('utf-8'))['cpro_layout']
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(f'Rebuilt {len(cards)} CPRO cards, exact pixel verification; {count} sectors')


if __name__ == '__main__':
    main()
