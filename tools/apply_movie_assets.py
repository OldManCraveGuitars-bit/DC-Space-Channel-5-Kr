"""Apply verified same-sized movies to the generated localized track."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sc5.disc import GDImage,SECTOR,PAYLOAD
from sc5.editor_project import Project
from sc5.movie_assets import registered_movies
from sc5.sector import verify_mode1,update_mode1


def main():
    project=Project(ROOT)
    paths,records=registered_movies(project)
    track=ROOT/'work/poc/Track5_KR.bin'
    changes=0
    with GDImage(project.disc,track3=ROOT/'work/poc/Track3_KR.bin',track5=track) as disc:
        entries={e.name:e for e in disc.entries()}
        # Validate every existing movie before changing any generated sector.
        for row in records:
            e=entries[row['name']]
            assert e.size==row['original_size']
            assert hashlib.sha256(disc.read(e.lba,e.size)).hexdigest() in (row['original_sha256'],row['sha256'])
        with track.open('r+b') as stream:
            for row in records:
                e=entries[row['name']];blob=paths[e.name].read_bytes()
                for offset in range(0,len(blob),PAYLOAD):
                    position=(e.lba+offset//PAYLOAD-disc.track5_start)*SECTOR
                    stream.seek(position);sector=stream.read(SECTOR)
                    assert verify_mode1(sector)
                    payload=bytearray(sector[16:16+PAYLOAD]);count=min(PAYLOAD,len(blob)-offset)
                    if payload[:count]==blob[offset:offset+count]:continue
                    payload[:count]=blob[offset:offset+count]
                    changed=update_mode1(sector,payload);assert verify_mode1(changed)
                    stream.seek(position);stream.write(changed);changes+=1
    manifest=ROOT/'work/poc/text_build.json'
    data=json.loads(manifest.read_text('utf-8'));data['movie_replacements']=records
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'Updated {changes} generated movie sectors; original disc untouched')


if __name__=='__main__':main()
