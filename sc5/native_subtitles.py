"""Build a freestanding SH-4 payload and patch a separate Korean disc candidate."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

from .paths import project_root
ROOT = project_root()
from sc5.editor_project import Project
from sc5.disc import GDImage, SECTOR, PAYLOAD
from sc5.patch_disc import write_cue
from .paths import resource_path
from sc5.sector import update_mode1, verify_mode1

BASE = 0x8c010000
PAYLOAD_BASE = 0x8c250000
HOOKS = [(0x8c06c460, 'frame'), (0x8c056718, 'voice_start'),
         (0x8c056060, 'voice_stop'), (0x8c0570aa, 'movie_start'),
         (0x8c057280, 'movie_stop'), (0x8c028fe8, 'options'),
         (0x8c021930, 'judgment'), (0x8c021732, 'judgment_alt'),
         (0x8c01073c, 'vmu_result'), (0x8c0106c8, 'vmu_completion'), (0x8c0539d8, 'hud')]

def generate_data(config, out):
    characters = sorted(set(''.join(c['korean'] for v in config['clips'].values() for c in v)) | set('실기 자막 테스트'))
    characters = [c for c in characters if c != '\n']
    ids = {c:i for i,c in enumerate(characters)}
    font = ImageFont.truetype(config['font'], 22)
    rectangles, glyphs = [], []
    preview = Image.new('RGB', (640, 56), '#303030')
    pd = ImageDraw.Draw(preview)
    pd.text((16,8), '실기 자막 테스트 — 영덕 블루로드', font=font, fill='white')
    preview.save(out/'font-preview.png')
    for c in characters:
        advance = math.ceil(font.getlength(c))
        image = Image.new('L',(max(advance,24),28))
        ImageDraw.Draw(image).text((0,0),c,font=font,fill=255)
        # Merge identical horizontal runs vertically into solid rectangles.
        first = len(rectangles); active = {}
        for y in range(28):
            runs = []; x = 0
            while x < image.width:
                if image.getpixel((x,y)) < 128: x += 1; continue
                start = x
                while x < image.width and image.getpixel((x,y)) >= 128: x += 1
                runs.append((start,x-start))
            current = {}
            for x,w in runs:
                if (x,w) in active:
                    index = active[(x,w)]; rectangles[index][3] += 1
                else:
                    index = len(rectangles); rectangles.append([x,y,w,1])
                current[(x,w)] = index
            active = current
        glyphs.append([first,len(rectangles)-first,advance,0])
    texts, cues, bindings, movie_names, movie_binding = [], [], [], [], []
    afs = {v:int(k) for k,v in config['afs_bases'].items()}
    for key, rows in config['clips'].items():
        first = len(cues)
        for row in rows:
            if not row.get('korean'): continue
            start = len(texts)
            texts.extend(0xffff if c == '\n' else ids[c] for c in row['korean'])
            cues.append([round(row['start']*1000),round(row['end']*1000),start,len(texts)-start,
                         round(row.get('bottom_offset',80)),0])
        if len(cues) == first: continue
        if key.startswith('movie:'):
            movie_names.append(key.split(':',1)[1].lower()); movie_binding.append(len(bindings))
            archive, member = 0, 0
        else:
            archive_name, number = key.rsplit(':',1); archive, member = afs[archive_name], int(number)
        duration = max(config['durations'].get(key,0)*1000,max(c[1] for c in cues[first:]))
        bindings.append([archive,math.ceil(duration),member,first,len(cues)-first,0])
    diagnostic_first = len(texts)
    texts.extend(ids[c] for c in '실기 자막 테스트')
    def array(typ,name,rows):
        return f'static const {typ} {name}[] = {{\n'+''.join('    {'+','.join(map(str,r))+'},\n' for r in rows)+'};\n'
    text = f'#define BINDING_COUNT {len(bindings)}\n#define MOVIE_COUNT {len(movie_names)}\n'
    text += f'#define NATIVE_BOX_COLOR 0x{config.get("caption_box_alpha",115)<<24:08x}u\n'
    text += array('Rect','glyph_rects',rectangles)+array('Glyph','glyphs',glyphs)+array('Cue','cues',cues)+array('Binding','bindings',bindings)
    text += 'static const u16 text_ids[] = {'+','.join(map(str,texts))+'};\n'
    text += 'static const char *const movie_names[] = {'+','.join(json.dumps(s) for s in movie_names)+'};\n'
    text += 'static const u16 movie_binding[] = {'+','.join(map(str,movie_binding))+'};\n'
    text += f'static const Cue diagnostic_cue = {{0,0xffffffff,{diagnostic_first},9,80,0}};\n'
    (out/'generated_data.h').write_text(text,'utf-8')
    (out/'cue-map.json').write_text(json.dumps({'bindings':list(config['clips']), 'glyphs':characters,
           'glyph_rectangles':len(rectangles),'cues':len(cues),'text_ids':len(texts)},ensure_ascii=False,indent=2),'utf-8')
    return {'glyphs':len(glyphs),'rectangles':len(rectangles),'cues':len(cues),'bindings':len(bindings)}

def trampolines(original, out):
    code = ['.section .text.trampolines,"ax"', '.align 2']
    for address,name in HOOKS:
        length = 12 if address % 4 == 0 else 14
        code += [f'.global _original_{name}', f'_original_{name}:']
        literals = []
        for offset in range(0,length,2):
            w = struct.unpack_from('<H',original,address-BASE+offset)[0]
            if w >> 12 == 13:
                lit_address = ((address+offset+4)&~3)+(w&255)*4
                value = struct.unpack_from('<I',original,lit_address-BASE)[0]
                label = f'lit_{name}_{offset}'
                code.append(f'    mov.l {label},r{(w>>8)&15}')
                literals.append((label,value))
            elif w >> 12 == 9 or w >> 12 in (10,11) or (w & 0xff00) in (0x8900,0x8b00,0x8d00,0x8f00):
                raise ValueError(f'Unsupported displaced instruction {hex(w)} at {hex(address+offset)}')
            else: code.append(f'    .word 0x{w:04x}')
        code += [f'    mov.l resume_{name},r1', '    jmp @r1', '    nop', '    .align 2',
                 f'resume_{name}: .long 0x{address+length:08x}']
        code.extend(f'{label}: .long 0x{v:08x}' for label,v in literals)
    (out/'hooks.S').write_text('\n'.join(code)+'\n','ascii')

def run(args, **kwargs):
    result = subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,**kwargs)
    if result.returncode: raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result.stdout

def build(diagnostic=False, disc=True):
    out = ROOT/'work/native-rom'/('diagnostic' if diagnostic else 'build')
    out.mkdir(parents=True,exist_ok=True)
    original = Project(ROOT).disc_bytes('1ST_READ.BIN')
    assert len(original)==0x260000 and not any(original[0x240000:])
    saved = ROOT/'work/runtime/original-1ST_READ.BIN'
    assert original == saved.read_bytes(), 'Original executable mismatch'
    config = json.loads((ROOT/'work/runtime/config.json').read_text('utf-8'))
    # Archive identifiers are physical LBAs + 150. Texture storage may relocate
    # files in the generated filesystem; bind against that directory.
    with GDImage(Project(ROOT).disc,track3=ROOT/'work/poc/Track3_KR.bin',
                 track5=ROOT/'work/poc/Track5_KR.bin') as localized:
        config['afs_bases']={str(e.lba+150):e.name.upper() for e in localized.entries()
                             if e.name.upper().endswith('.AFS')}
        from .judgment_assets import prepare
        title_entry, title_bytes, judgment_art = prepare(Project(ROOT),localized,out)
        title_source_hash = hashlib.sha256(localized.read(title_entry.lba,title_entry.size)).hexdigest()
    stats = generate_data(config,out); trampolines(original,out)
    from .compact_hud import prepare as prepare_hud
    _, _, hud_art = prepare_hud(Project(ROOT),out)
    toolchain = ROOT/'work/native-rom/toolchain/sh-elf/sh-elf/bin'
    gcc = toolchain/'sh-elf-gcc.exe'
    flags = ['-ml','-m4-single-only','-mdiv=call-div1','-Os','-ffreestanding','-fno-builtin','-fno-pic','-fno-common','-fno-unwind-tables','-fno-asynchronous-unwind-tables']
    if diagnostic: flags += ['-DNATIVE_DIAGNOSTIC_CUE=1']
    run([gcc,*flags,'-I',out,'-c',resource_path('native/subtitles.c'),'-o',out/'subtitles.o'])
    run([gcc,*flags,'-I',out,'-c',resource_path('native/judgment.c'),'-o',out/'judgment.o'])
    run([gcc,*flags,'-I',out,'-c',resource_path('native/judgment_vmu.c'),'-o',out/'judgment_vmu.o'])
    run([gcc,*flags,'-I',out,'-c',resource_path('native/hud.c'),'-o',out/'hud.o'])
    run([gcc,*flags,'-c',out/'hooks.S','-o',out/'hooks.o'])
    run([gcc,*flags,'-nostdlib','-Wl,-T,'+str(resource_path('native/link.ld')),'-Wl,-Map,'+str(out/'payload.map'),
         out/'subtitles.o',out/'judgment.o',out/'judgment_vmu.o',out/'hud.o',out/'hooks.o','-lgcc','-o',out/'payload.elf'])
    run([toolchain/'sh-elf-objcopy.exe','-O','binary',out/'payload.elf',out/'payload.bin'])
    symbols={}
    for line in run([toolchain/'sh-elf-nm.exe','-n',out/'payload.elf']).splitlines():
        fields=line.split()
        if len(fields)==3:symbols[fields[2].removeprefix('_')]=int(fields[0],16)
    (out/'payload-disassembly.txt').write_text(run([toolchain/'sh-elf-objdump.exe','-d',out/'payload.elf']),'utf-8')
    payload=(out/'payload.bin').read_bytes()
    patched=bytearray(original)
    # Original SAVE title UV stops six pixels before the E's outer edge.
    # Keep the original English atlas and extend only that sprite's UV width.
    save_uv_address=0x8c03acf8
    save_uv_offset=save_uv_address-BASE
    assert original[save_uv_offset:save_uv_offset+4]==struct.pack('<f',390/512)
    assert original[save_uv_offset-16:save_uv_offset-8]==struct.pack('<IHH',114,512,512)
    patched[save_uv_offset:save_uv_offset+4]=struct.pack('<f',396/512)
    from .warning_layout import patch_warning_layout
    warning_repairs = patch_warning_layout(original, patched, Project(ROOT))
    from .profile_layout import patch_profile_layout
    profile_repairs = patch_profile_layout(original, patched, Project(ROOT))
    assert len(payload)<=0x20000 and symbols['payload_end']<=0x8c270000
    patched[0x240000:0x240000+len(payload)]=payload
    hooks=[]
    for address,name in HOOKS:
        length=12 if address%4==0 else 14
        target=symbols[f'native_{name}']
        # Aligned literal at offset 8 or 10, disp always 1 or 2 respectively.
        words=[0xd001 if length==12 else 0xd002,0x402b,0x0009,0x0009]
        if length==14:words.append(0x0009)
        stub=struct.pack('<'+'H'*len(words),*words)+struct.pack('<I',target)
        assert len(stub)==length
        old=original[address-BASE:address-BASE+length]
        patched[address-BASE:address-BASE+length]=stub
        hooks.append({'address':hex(address),'target':hex(target),'original':old.hex(),'patched':stub.hex()})
    (out/'1ST_READ.BIN').write_bytes(patched)
    report={'diagnostic':diagnostic,'source_sha256':hashlib.sha256(original).hexdigest(),
      'executable_sha256':hashlib.sha256(patched).hexdigest(),'payload_size':len(payload),
      'ram_end':hex(symbols['payload_end']),'diagnostics_address':hex(symbols['native_diagnostics']),
      'localized_afs_bases':config['afs_bases'],
      'stats':stats,'hooks':hooks,'judgment_art':judgment_art,'hud_art':hud_art,
      'layout_repairs':[{'asset':'SAVE English title','address':hex(save_uv_address),
                        'original_right_u':390,'corrected_right_u':396,'atlas_width':512,
                        'original_English_bitmap_preserved':True}] + warning_repairs + profile_repairs,
      'emulator_services':False,'symbols':{k:hex(v) for k,v in symbols.items() if k.startswith(('native','original'))}}
    if disc:
        source_track=ROOT/'work/poc/Track5_KR.bin'
        track=out/'Track5_NATIVE_KR.bin'
        state_path=out/'disc-state.json'
        state=json.loads(state_path.read_text('utf-8')) if state_path.exists() else {}
        source_hash=hashlib.file_digest(source_track.open('rb'),'sha256').hexdigest()
        if not track.exists() or state.get('source_track_sha256') != source_hash:
            shutil.copyfile(source_track,track)
            state={'source_track_sha256':source_hash,'executable_sha256':report['source_sha256']}
        from sc5.cli import DEFAULT_DISC
        with GDImage(DEFAULT_DISC) as image:
            entry=next(e for e in image.entries() if e.name=='1ST_READ.BIN')
            changes=0
            with track.open('r+b') as f:
                current_exec=bytearray()
                for offset in range(0,len(patched),PAYLOAD):
                    f.seek((entry.lba+offset//PAYLOAD-image.track5_start)*SECTOR)
                    raw=f.read(SECTOR)
                    if not verify_mode1(raw):raise ValueError('Candidate executable sector fails EDC/ECC')
                    current_exec.extend(raw[16:16+min(PAYLOAD,len(patched)-offset)])
                if hashlib.sha256(current_exec).hexdigest() != state['executable_sha256']:
                    raise ValueError('Candidate executable differs from the recorded build')
                for offset in range(0,len(patched),PAYLOAD):
                    lba=entry.lba+offset//PAYLOAD
                    pos=(lba-image.track5_start)*SECTOR
                    f.seek(pos); raw=f.read(SECTOR)
                    if not verify_mode1(raw):raise ValueError(f'Invalid EDC/ECC at {lba}')
                    size=min(PAYLOAD,len(patched)-offset)
                    current=raw[16:16+size]
                    # Rebuilding either candidate is allowed only from previous known native output or original.
                    if current==patched[offset:offset+size]:continue
                    block=bytearray(raw[16:16+PAYLOAD]);block[:size]=patched[offset:offset+size]
                    update=update_mode1(raw,block)
                    assert verify_mode1(update)
                    f.seek(pos);f.write(update);changes+=1
                # Only the unused options-atlas region is new artwork. Other
                # localized TITLE members come from the existing approved disc.
                current_title=bytearray()
                for offset in range(0,len(title_bytes),PAYLOAD):
                    f.seek((title_entry.lba+offset//PAYLOAD-image.track5_start)*SECTOR)
                    raw=f.read(SECTOR)
                    assert verify_mode1(raw)
                    current_title.extend(raw[16:16+min(PAYLOAD,len(title_bytes)-offset)])
                expected_title=state.get('judgment_title_sha256',title_source_hash)
                if hashlib.sha256(current_title).hexdigest()!=expected_title:
                    raise ValueError('Candidate options textures differ from the recorded build')
                for offset in range(0,len(title_bytes),PAYLOAD):
                    pos=(title_entry.lba+offset//PAYLOAD-image.track5_start)*SECTOR
                    f.seek(pos);raw=f.read(SECTOR)
                    size=min(PAYLOAD,len(title_bytes)-offset)
                    if raw[16:16+size]==title_bytes[offset:offset+size]:continue
                    block=bytearray(raw[16:16+PAYLOAD]);block[:size]=title_bytes[offset:offset+size]
                    update=update_mode1(raw,block);assert verify_mode1(update)
                    f.seek(pos);f.write(update);changes+=1
                state['judgment_title_sha256']=hashlib.sha256(title_bytes).hexdigest()
            write_cue(image,track,out/'Track5_NATIVE_KR.cue',track3_override=ROOT/'work/poc/Track3_KR.bin')
        report['patched_sectors']=changes
        report['cue']=str(out/'Track5_NATIVE_KR.cue')
        state['executable_sha256']=report['executable_sha256']
        state_path.write_text(json.dumps(state,indent=2)+'\n','utf-8')
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('symbols','hooks')},ensure_ascii=False,indent=2))
    return report

def package_rom(chd=True, output_dir=None, chd_path=None):
    """Package the native executable and localized assets as GDI and one CHD."""
    project=Project(ROOT)
    out=Path(output_dir) if output_dir else ROOT/'output/native-rom'
    out.mkdir(parents=True,exist_ok=True)
    tracks=[]
    with GDImage(project.disc) as image:
        s1=next(image.cue_dir.glob('*Track 1).bin')).stat().st_size//SECTOR
        fourth=image.volume_start+image.track3_sectors
        # Track 5's INDEX 00 contains live MODE1 data (MANATEE.DRV and the
        # beginning of SH_1.MLT). Preserve every sector and map from INDEX 00.
        # Trimming the nominal 450-sector pregap silently removes game data.
        starts={1:0,2:s1+150,3:image.volume_start,4:fourth+150,5:image.track5_start}
        for n,skip in [(1,0),(2,150),(3,0),(4,150),(5,0)]:
            source=next(image.cue_dir.glob(f'*Track {n}).bin'))
            if n==3:source=ROOT/'work/poc/Track3_KR.bin'
            if n==5:source=ROOT/'work/native-rom/build/Track5_NATIVE_KR.bin'
            dest=out/f'track{n:02d}.bin'
            with source.open('rb') as r,dest.open('wb') as w:
                r.seek(skip*SECTOR);shutil.copyfileobj(r,w)
            assert dest.stat().st_size==source.stat().st_size-skip*SECTOR
            tracks.append(f'{n} {starts[n]} {4 if n in (1,3,5) else 0} 2352 {dest.name} 0')
    gdi=out/'Space Channel 5 Korean Native.gdi'
    gdi.write_text('5\n'+'\n'.join(tracks)+'\n','ascii')
    report={'gdi':str(gdi),'subtitles_embedded':True,'external_caption_files':False,
            'track5_index00_data_preserved':True,'track5_start_lba':starts[5]}
    if chd:
        tool=ROOT/'work/native-rom/toolchain/mame/chdman.exe'
        target=Path(chd_path) if chd_path else ROOT/'output/Space Channel 5 Korean Native.chd'
        pending=target.with_suffix('.pending.chd')
        run([tool,'createcd','-i',gdi,'-o',pending,'-f','-np','8'])
        verification=run([tool,'verify','-i',pending])
        pending.replace(target)
        report.update(chd=str(target),verification=verification,
            chd_sha256=hashlib.file_digest(target.open('rb'),'sha256').hexdigest())
    (out/'package-report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    return report

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic',action='store_true')
    parser.add_argument('--no-disc',action='store_true')
    args=parser.parse_args()
    build(args.diagnostic,not args.no_disc)

if __name__=='__main__': main()
