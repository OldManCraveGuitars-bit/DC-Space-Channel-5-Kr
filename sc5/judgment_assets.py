"""Draw the judgment row from original glyphs without texture compression."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageFilter
from .assets import decode_pvr


def components(mask):
    seen = np.zeros(mask.shape, bool)
    result = []
    for yy, xx in zip(*np.nonzero(mask)):
        if seen[yy, xx]:
            continue
        todo, points = [(yy, xx)], []
        seen[yy, xx] = True
        while todo:
            y, x = todo.pop()
            points.append((y, x))
            for ny, nx in ((y-1,x), (y+1,x), (y,x-1), (y,x+1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx] = True
                    todo.append((ny,nx))
        if len(points) < 30:
            continue
        py, px = zip(*points)
        left, top, right, bottom = min(px), min(py), max(px)+1, max(py)+1
        glyph = np.zeros((bottom-top, right-left), np.uint8)
        for y,x in points:
            glyph[y-top,x-left] = 255
        result.append((left, Image.fromarray(glyph)))
    return sorted(result, key=lambda v:v[0])


def pink_core(image, top, bottom):
    a = np.asarray(image)[top:bottom].astype(int)
    r,g,b,alpha = a.transpose(2,0,1)
    return (r>245)&(g>=110)&(g<175)&(b<230)&(alpha>200)


def styled(core):
    """Original pink fill, white keyline and dark pink outer stroke."""
    mask = Image.new('L', (core.width+8,26))
    mask.paste(core, (4,4))
    out = Image.new('RGBA', mask.size)
    for color, layer in [((136,0,119,255),mask.filter(ImageFilter.MaxFilter(7))),
                         ((255,255,255,255),mask.filter(ImageFilter.MaxFilter(5)))]:
        out.paste(color, (0,0), layer)
    for y in range(26):
        fill = (255,153,204,255) if y < 13 else (255,136,187,255)
        strip = mask.crop((0,y,mask.width,y+1))
        out.paste(fill, (0,y,mask.width,y+1), strip)
    return out


def original_glyphs(image,top,bottom,letters):
    mask=pink_core(image,top,bottom)
    pieces=components(mask)
    assert len(pieces)==len(letters)
    result={}
    for c,(left,core) in zip(letters,pieces):
        width=core.width+8
        yy,xx=np.indices((26,width))
        own=np.asarray(core)>0
        py,px=np.nonzero(own)
        distance=((yy[...,None]-py-4)**2+(xx[...,None]-px-4)**2).min(axis=2)
        local=mask[:,max(0,left-4):left+core.width+4].copy()
        core_left=left-max(0,left-4)
        local[4:4+core.height,core_left:core_left+core.width][own]=False
        oy,ox=np.nonzero(local)
        allowed=distance<=16
        if len(oy):
            other=((yy[...,None]-oy)**2+(xx[...,None]-ox)**2).min(axis=2)
            allowed &= distance<=other
        crop=image.crop((left-4,top, left+core.width+4,top+26))
        a=np.asarray(crop).copy()
        a[~allowed]=0
        result.setdefault(c,(Image.fromarray(a),core.width-3))
    return result


def rects(image):
    """Exact 4-bit RGBA pixels, merged only when color and extent match."""
    rgba=(np.asarray(image.convert('RGBA'),dtype=np.uint32)+8)//17
    r,g,b,a=rgba.transpose(2,0,1)
    words=(a<<12)|(r<<8)|(g<<4)|b
    rows=[];active={}
    for y in range(image.height):
        current={};x=0
        while x<image.width:
            color=int(words[y,x])
            if not color>>12:x+=1;continue
            start=x
            while x<image.width and words[y,x]==color:x+=1
            key=(start,x-start,color)
            if key in active:
                index=active[key];rows[index][3]+=1
            else:
                index=len(rows);rows.append([start,y,x-start,1,color])
            current[key]=index
        active=current
    return sorted(rows,key=lambda r:r[4])


def spaced_label(glyphs, text):
    """Retain SET's original tracking and loosen JUDGMENT by 1.28px.

    Use the original italic advances, with only two source pixels added
    between JUDGMENT letters. Crop to the full visible extent of the final T.
    """
    canvas=Image.new('RGBA',(500,26))
    placements=[];x=0;judgment=False
    for index,letter in enumerate(text):
        if letter==' ':
            x+=13;judgment=True
            continue
        source,advance=glyphs['T_END' if index==len(text)-1 else letter]
        canvas.alpha_composite(source,(x,0))
        placements.append({'letter':letter,'source_x':x,'source_width':source.width})
        x+=advance+(2 if judgment and index<len(text)-1 else 0)
    width=max(canvas.getbbox()[2]+2,placements[-1]['source_x']+placements[-1]['source_width']+2)
    assert width<canvas.width
    label=canvas.crop((0,0,width,26)).resize((round(width*.64),17),Image.Resampling.LANCZOS)
    return label,placements


def prepare(project, localized, out):
    item = project.item('images','TITLE.PVM:082')
    original = project.disc_bytes('TITLE.PVM',item['offset'],item['size'])
    title = decode_pvr(original).convert('RGBA')
    common = project.item('images','COMMON_DATA.PVM:113')
    font = decode_pvr(project.disc_bytes(common['archive'],common['offset'],common['size'])).convert('RGBA')
    glyphs = {};full={}
    for source, top, bottom, letters in [(title,44,70,'DEVICEOPTIONS'),
                                         (font,136,162,'RESULTGAMEOVER')]:
        pieces = components(pink_core(source,top,bottom))
        assert len(pieces) == len(letters)
        for c,(_,mask) in zip(letters,pieces):
            glyphs.setdefault(c,mask)
        for c,value in original_glyphs(source,top,bottom,letters).items():
            full.setdefault(c,value)
    # J uses the original U's right stem and bottom curve, with its upper-left
    # stem removed. No replacement font is introduced into the existing art.
    j = np.asarray(glyphs['U']).copy()
    for y in range(12):
        j[y,:int(j.shape[1]*0.52)] = 0
    glyphs['J'] = Image.fromarray(j)
    full['J']=(styled(glyphs['J']),glyphs['J'].width-3)
    # The source T shares its right outline with the next original letter.
    # Rebuild that keyline from T's original fill so its tip stays complete
    # when the glyph stands alone at the end of JUDGMENT.
    full['T_END']=(styled(glyphs['T']),glyphs['T'].width+8)
    label,placements=spaced_label(full,'SET JUDGMENT')
    digits=[]
    bounds = [(54,84),(86,126),(128,170),(172,214),(216,256),(258,300)]
    blue_basis=np.array([[0,85,170],[51,170,204],[255,255,255]],float)
    pink_basis=np.array([[136,0,119],[255,136,187],[255,255,255]],float)
    for i,(left,right) in enumerate(bounds):
        digit=font.crop((left,458,right,484))
        a=np.asarray(digit).copy()
        weights=np.asarray(a[:,:,:3],float)@np.linalg.inv(blue_basis)
        weights=np.clip(weights,0,1)
        weights/=np.maximum(weights.sum(axis=2,keepdims=True),1e-8)
        color=np.rint(weights@pink_basis).clip(0,255).astype(np.uint8)
        a[:,:,:3]=color
        a[np.max(color,axis=2)<30]=0
        digit=Image.fromarray(a)
        digit=digit.crop(digit.getbbox())
        width=max(10,round(digit.width*.64))
        digit=digit.resize((width,17),Image.Resampling.LANCZOS)
        cell=Image.new('RGBA',(23,17));cell.alpha_composite(digit,((23-width)//2,0))
        digits.append(cell)
    digit_start=label.width+15
    preview=Image.new('RGBA',(digit_start+6*24,24))
    preview.alpha_composite(label,(0,3))
    for i,digit in enumerate(digits):preview.alpha_composite(digit,(digit_start+i*24,3))
    pieces=[label]+digits
    row_y=208
    approved=None
    config_path=project.root/'data/judgment_artwork.json'
    if config_path.exists():
        spec=json.loads(config_path.read_text('utf-8'))
        source=project.root/spec['source']
        with Image.open(source) as supplied:
            if list(supplied.size)!=spec['canvas']:
                raise ValueError('Approved judgment PNG dimensions changed')
            preview=supplied.convert('RGBA')
        digit_start=spec['digits_start_x']
        digit_step=spec['digit_step']
        if digit_step!=24 or digit_start+6*digit_step!=preview.width or preview.height>31:
            raise ValueError('Invalid judgment label/digit layout')
        label=preview.crop((0,0,digit_start,preview.height))
        digits=[preview.crop((digit_start+i*digit_step,0,digit_start+(i+1)*digit_step,preview.height)) for i in range(6)]
        pieces=[label]+digits
        row_y=spec['render_y']
        approved={'source':spec['source'],'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'source_size':list(preview.size),'source_resampled':False,
                  'source_cleanup':False,'source_layout_preserved':True}
    preview.save(out/'judgment-row-lossless.png')
    preview.resize((preview.width*4,preview.height*4),Image.Resampling.NEAREST).save(out/'judgment-row-spacing-4x.png')
    entry = next(e for e in localized.entries() if e.name=='TITLE.PVM')
    archive = bytearray(localized.read(entry.lba,entry.size))
    assert archive[item['offset']:item['offset']+item['size']] == original
    # The original texture archive is left byte-identical. New menu glyphs are
    # native colored PVR rectangles, so neither VQ nor an enlarged atlas is used.
    (out/'TITLE-JUDGMENT.PVM').write_bytes(archive)
    all_rows=[];ranges=[]
    for image in pieces:
        rows=rects(image);ranges.append((len(all_rows),len(rows)));all_rows.extend(rows)
    header=f'#define JUDGMENT_DIGIT_X {56+digit_start}\n#define JUDGMENT_ROW_Y {row_y}\nstatic const MenuPixel judgment_pixels[] = {{\n'
    for x,y,w,h,color in all_rows:
        packed=x|(y<<9)|(w<<14)|(h<<23)
        header+=f'    {{0x{packed:08x}u,0x{color:04x}u}},\n'
    header+='};\nstatic const MenuRange judgment_ranges[] = {\n'
    header+=''.join(f'    {{{first},{count}}},\n' for first,count in ranges)+'};\n'
    (out/'judgment_pixels.h').write_text(header,'ascii')
    report={'VQ_used':False,'original_texture_archive_byte_exact':True,
            'packing_mode':'native_argb4444_pixels','glyph_source':'original_game_glyphs',
            'rectangles':len(all_rows),'label':'SET JUDGMENT 1 2 3 4 5 6',
            'label_width':label.width,'digit_x':56+digit_start,
            'set_original_tracking':True,'judgment_added_tracking_pixels':1.28,
            'letter_placements':placements,
            'last_glyph_fully_preserved':True}
    if approved:
        report.update(glyph_source='user_approved_png',approved_png=approved,
                      label_width=label.width,digit_x=56+digit_start,row_y=row_y)
        for generated_only in ('set_original_tracking','judgment_added_tracking_pixels','letter_placements','last_glyph_fully_preserved'):
            report.pop(generated_only,None)
    # Reconstruct the submitted rectangles to catch cropped pixels or an
    # accidental shift in the six separately selectable digit cells.
    restored=np.zeros((preview.height,preview.width),np.uint16)
    for index,image in enumerate(pieces):
        x_offset=0 if index==0 else digit_start+(index-1)*24
        y_offset=0 if approved else 3
        for x,y,w,h,color in rects(image):
            restored[y_offset+y:y_offset+y+h,x_offset+x:x_offset+x+w]=color
    quantized=(np.asarray(preview,dtype=np.uint32)+8)//17
    r,g,b,a=quantized.transpose(2,0,1)
    expected=(a<<12)|(r<<8)|(g<<4)|b
    expected[a==0]=0
    if not np.array_equal(restored,expected):raise ValueError('Judgment PNG packing changed its layout')
    report['all_pixels_match_argb4444']=True
    (out/'judgment-art-report.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    return entry,bytes(archive),report
