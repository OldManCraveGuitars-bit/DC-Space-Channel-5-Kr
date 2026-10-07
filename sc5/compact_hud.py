"""Lossless Korean HUD overlays in a small hardware-paletted texture."""
from __future__ import annotations
import hashlib, json, struct
import numpy as np
from PIL import Image
from .assets import decode_pvr, encode_vq_regions, pvm_members

GLOBAL_ID = 0x4b520001
PLACEMENTS = [(2,2),(2,25),(2,48),(194,2),(194,24),(194,46),(388,2),(388,35),(194,70)]
BANKS = [0,0,0,1,1,1,2,0,1]


def prepare(project, out):
    item = project.item('images', 'COMMON_DATA.PVM:114')
    record = project.edits('images')[item['id']]
    original = project.disc_bytes(item['archive'], item['offset'], item['size'])
    source_path = project.replacement('images', item['id'])
    image = Image.open(source_path).convert('RGBA')
    channels = (np.asarray(image, dtype=np.uint32)+8)//17
    r,g,b,a = channels.transpose(2,0,1)
    words = ((a<<12)|(r<<8)|(g<<4)|b).astype(np.uint16)
    words[a==0] = 0
    regions = record['edit_regions']
    assert len(regions) == 9
    crops, palettes, maps = [], [set([0]) for _ in range(3)], []
    for i,(x,y,w,h) in enumerate(regions):
        alpha = Image.fromarray((words[y:y+h,x:x+w]>>12).astype(np.uint8))
        bounds = alpha.getbbox()
        assert bounds
        x0,y0,x1,y1 = bounds
        crop = words[y+y0:y+y1,x+x0:x+x1]
        crops.append(crop)
        palettes[BANKS[i]].update(crop.ravel().tolist())
        px,py = PLACEMENTS[i]
        assert px>0 and py>0 and px+crop.shape[1]<512 and py+crop.shape[0]<128
        maps.append([x+x0,y+y0,crop.shape[1],crop.shape[0],px,py,BANKS[i]])
    palettes = [sorted(p) for p in palettes]
    assert all(len(p)<=256 and p[0]==0 for p in palettes)
    encoded = np.zeros((128,512),np.uint8)
    occupied = np.zeros((128,512),bool)
    for crop,(sx,sy,w,h,x,y,bank) in zip(crops,maps):
        assert not occupied[y-1:y+h+1,x-1:x+w+1].any()
        lookup = {color:index for index,color in enumerate(palettes[bank])}
        indices = np.array([lookup[int(color)] for color in crop.ravel()],np.uint8).reshape(h,w)
        encoded[y:y+h,x:x+w] = indices
        occupied[y:y+h,x:x+w] = True
        assert np.array_equal(np.asarray(palettes[bank],np.uint16)[indices],crop)
    # Rectangular twiddle: 128x128 squares laid out horizontally.
    yy,xx = np.indices(encoded.shape)
    order = (xx//128)*128*128
    for bit in range(7):
        order |= ((yy>>bit)&1)<<(bit*2)
        order |= ((xx>>bit)&1)<<(bit*2+1)
    twiddled = np.empty(encoded.size,np.uint8)
    twiddled[order.ravel()] = encoded.ravel()
    packed = bytearray(b'PVRT'+struct.pack('<I',8+encoded.size)+bytes([6,7,0,0])+struct.pack('<HH',512,128)+twiddled.tobytes())
    packed += bytes((-len(packed))%32)
    struct.pack_into('<I',packed,4,len(packed)-8)
    blank = decode_pvr(original)
    for x,y,w,h in regions:
        blank.paste((0,0,0,0),(x,y,x+w,y+h))
    cleared, audit = encode_vq_regions(original,blank,regions)
    assert audit['outside_regions_exact'] and audit['premultiplied_rmse']==0
    out.mkdir(parents=True,exist_ok=True)
    (out/'hud-overlay.pvr').write_bytes(packed)
    (out/'hud-cleared.pvr').write_bytes(cleared)
    header = '#define HUD_GLOBAL_ID 0x%08xu\n'%GLOBAL_ID
    header += 'static const unsigned short hud_palette[3][256] = {\n'
    for palette in palettes:
        header += '{'+','.join('0x%04x'%v for v in palette+[0]*(256-len(palette)))+'},\n'
    header += '};\nstatic const HudMap hud_maps[] = {\n'
    header += ''.join('{'+','.join(map(str,m))+'},\n' for m in maps)+'};\n'
    (out/'hud_overlay.h').write_text(header,'ascii')
    report = {'source_png':str(source_path),'source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
        'source_retouching':False,'source_resampling':False,'ARGB4444_pixels_exact':True,
        'palette_sizes':list(map(len,palettes)),'overlay_vram_bytes':65536,
        'old_uncompressed_hud_vram_bytes':524288,'restored_VQ_hud_vram_bytes':67584,
        'maps':maps,'global_id':hex(GLOBAL_ID),'cleared_original':audit}
    (out/'hud-overlay-proof.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    return cleared,bytes(packed),report


def append_overlay(archive, overlay):
    count = struct.unpack_from('<H',archive,10)[0]
    first = 8+struct.unpack_from('<I',archive,4)[0]
    assert count==292
    header = bytearray(archive[:12+count*38])
    name = b'korean_hud_overlay'.ljust(28,b'\0')
    header += struct.pack('<H',count)+name+bytes([6,7])+struct.pack('<H',0x79)+struct.pack('<I',GLOBAL_ID)
    header += bytes((16-len(header))%32)
    struct.pack_into('<I',header,4,len(header)-8)
    struct.pack_into('<H',header,10,count+1)
    tail = bytearray(archive[first:])
    last = pvm_members(archive,'COMMON_DATA.PVM')[-1]
    # The original final member omits the 16-byte padding used between members.
    # Include it in that chunk's declared length before adding a successor.
    padding = (16-(len(header)+len(tail)))%32
    if padding:
        offset = last['offset']-first
        struct.pack_into('<I',tail,offset+4,last['size']+padding-8)
        tail += bytes(padding)
    packed = bytes(header)+bytes(tail)+overlay
    members = pvm_members(packed,'COMMON_DATA.PVM')
    assert len(members)==count+1 and all((m['offset']+16)%32==0 for m in members)
    return packed
