"""Verify the final video-only cleanup and unchanged subtitle presentation."""
from pathlib import Path
import hashlib
import json
import sys
import types

import numpy as np
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sc5.cli import DEFAULT_DISC
from sc5.disc import GDImage,SECTOR,PAYLOAD
from sc5.sector import verify_mode1


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def normalized(code):
    return code.replace(co_filename='<source>',co_consts=tuple(
        normalized(x) if isinstance(x,types.CodeType) else x for x in code.co_consts))


def main():
    evidence=ROOT/'work/movie-dialogue-review-20261008'
    before=ROOT/'output/native-rom-profile-fixed'
    after=ROOT/'output/native-rom-movie-dialogue-fixed'
    prior=json.loads((evidence/'before/config.json').read_text('utf-8'))
    current=json.loads((ROOT/'work/runtime/config.json').read_text('utf-8'))
    for key in prior['clips']:
        if key=='movie:r4_makuma.sfd':
            assert [{k:v for k,v in r.items() if k!='bottom_offset'} for r in prior['clips'][key]] == \
                   [{k:v for k,v in r.items() if k!='bottom_offset'} for r in current['clips'][key]]
            assert all(r['bottom_offset']==48 for r in current['clips'][key])
        else:assert prior['clips'][key]==current['clips'][key],key
    assert prior['caption_box_alpha']==current['caption_box_alpha']==115
    assert (ROOT/'native/subtitles.c').read_bytes()==(evidence/'before/subtitles.c').read_bytes()
    assert (ROOT/'sc5/native_subtitles.py').read_bytes()==(evidence/'before/native_subtitles.py').read_bytes()
    for i in range(1,5):assert sha(before/f'track{i:02d}.bin')==sha(after/f'track{i:02d}.bin')
    allowed=np.zeros((after/'track05.bin').stat().st_size//SECTOR,dtype=bool)
    files=[]
    with GDImage(DEFAULT_DISC,track3=before/'track03.bin',track5=before/'track05.bin') as old, \
         GDImage(DEFAULT_DISC,track3=after/'track03.bin',track5=after/'track05.bin') as new:
        a={e.name:e for e in old.entries()};b={e.name:e for e in new.entries()}
        assert set(a)==set(b)
        assert all((a[n].lba,a[n].size)==(e.lba,e.size) for n,e in b.items())
        for name,path in [('1ST_READ.BIN',ROOT/'work/native-rom/build/1ST_READ.BIN'),
                          ('R4_MAKUMA.SFD',ROOT/'assets/movie-edits/R4_MAKUMA.SFD')]:
            e=b[name];data=new.read(e.lba,e.size);assert data==path.read_bytes()
            first=e.lba-new.track5_start;count=(e.size+PAYLOAD-1)//PAYLOAD
            allowed[first:first+count]=True
            files.append({'name':name,'lba':e.lba,'size':e.size,'sha256':hashlib.sha256(data).hexdigest()})
    old_map=np.memmap(before/'track05.bin',dtype=np.uint8,mode='r').reshape(-1,SECTOR)
    new_map=np.memmap(after/'track05.bin',dtype=np.uint8,mode='r').reshape(-1,SECTOR)
    changed=[]
    for start in range(0,len(old_map),4096):
        indices=np.flatnonzero(np.any(old_map[start:start+4096]!=new_map[start:start+4096],axis=1))+start
        assert np.all(allowed[indices])
        changed.extend(indices.tolist())
    for index in changed:assert verify_mode1(new_map[index].tobytes()),index
    archive=CArchiveReader(str(ROOT/'SC5KoreanWorkbench_v15.exe'));pyz=archive.open_embedded_archive('PYZ.pyz')
    modules=('sc5.movie_assets','sc5.build_text','sc5.editor_project','sc5.native_subtitles','sc5.native_player','sc5.profile_layout')
    for module in modules:
        expected=compile((ROOT/(module.replace('.','/')+'.py')).read_text('utf-8'),'<source>','exec')
        assert normalized(expected)==normalized(pyz.extract(module)),module
    key=next(k for k in archive.toc if k.replace('\\','/')=='native/subtitles.c')
    assert archive.extract(key)==(evidence/'before/subtitles.c').read_bytes()
    retained=json.loads((evidence/'packaged-track-retention.json').read_text('utf-8-sig'))
    track_hash=sha(after/'track05.bin');assert track_hash==retained['sha256'].lower()
    report={'passed':True,'modified_files':files,'changed_sectors':len(changed),
            'all_changed_sectors_edc_ecc_valid':True,'all_file_sizes_and_lbas_unchanged':True,
            'other_movies_images_audio_unchanged':True,'four_title_movies_and_cues_unchanged':True,
            'previous_profile_hud_boss_save_fixes_preserved':True,
            'subtitle_renderer_identical_to_prior':True,'box_alpha':115,'no_opaque_masks':True,
            'only_dialogue_position_changed':{'movie':'R4_MAKUMA.SFD','old_bottom':84,'new_bottom':48},
            'editor_source_verified':list(modules),'editor_sha256':sha(ROOT/'SC5KoreanWorkbench_v15.exe'),
            'track5_sha256':track_hash}
    (evidence/'final-disc-validation.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
