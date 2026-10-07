"""Use standard ARGB4444 textures and reclaim byte-identical audio storage."""
from pathlib import Path
import ctypes
import hashlib
import json
import struct
import numpy as np
from .assets import decode_pvr,pvm_members
from .disc import GDImage,SECTOR,PAYLOAD
from .paths import resource_path
from .sector import update_mode1,verify_mode1

def encode_common_atlas(original,image,regions):
    p=original.find(b'PVRT')
    w,h=struct.unpack_from('<HH',original,p+12)
    if p<0 or original[p+8]!=2 or (w,h)!=(512,512) or image.size!=(w,h):
        raise ValueError('Expected the 512x512 ARGB4444 COMMON atlas')
    prior=np.asarray(decode_pvr(original),dtype=np.uint32)
    source=np.asarray(image.convert('RGBA'),dtype=np.uint32)
    mask=np.zeros((h,w),bool)
    for x,y,rw,rh in regions:
        mask[y:y+rh,x:x+rw]=True
    def visual(a):
        a=a.astype(float)
        a[:,:,:3]*=a[:,:,3:]/255
        return a
    if np.any(np.abs(visual(prior)[~mask]-visual(source)[~mask])>1):
        raise ValueError('Visible pixels outside registered labels changed')
    target=source.copy(); target[~mask]=prior[~mask]
    channels=(target+8)//17
    r,g,b,a=(channels[:,:,i] for i in range(4))
    pixels=((a<<12)|(r<<8)|(g<<4)|b).astype('<u2')
    yy,xx=np.indices((h,w)); order=np.zeros((h,w),np.int32)
    for bit in range(9):
        order|=((yy>>bit)&1)<<(bit*2)
        order|=((xx>>bit)&1)<<(bit*2+1)
    twiddled=np.empty(w*h,dtype='<u2');twiddled[order.ravel()]=pixels.ravel()
    header=bytearray(original[:p+16]);header[p+9]=1
    struct.pack_into('<I',header,p+4,8+twiddled.nbytes)
    packed=bytes(header)+twiddled.tobytes()
    # The game's texture uploader consumes 32-byte DMA blocks. Preserve the
    # original member alignment: each PVRT header starts at 16 modulo 32,
    # and its data starts at 0. Omitting the original trailing padding shifts
    # every later member's data by 16 bytes and can corrupt subsequent uploads.
    padding=(-len(packed))%32
    packed+=bytes(padding)
    header=bytearray(packed[:p+16])
    struct.pack_into('<I',header,p+4,len(packed)-p-8)
    packed=bytes(header)+packed[p+16:]
    decoded=np.asarray(decode_pvr(packed))
    assert np.array_equal(decoded,channels.astype(np.uint8)*17)
    assert np.array_equal(decoded[~mask],prior[~mask])
    report={'packing_mode':'common_uncompressed','VQ_used':False,
            'pixel_format':'ARGB4444','source_bitmap_retouching':False,
            'outside_regions_pixel_exact':True,'per_pixel_quantization_only':True,
            'original_size':len(original),'new_size':len(packed),
            'member_alignment':32,'trailing_padding_bytes':padding,
            'source_premultiplied_rmse':float(np.mean((visual(source)-visual(decoded))**2)**.5)}
    return packed,report

def _codec():
    lib=ctypes.CDLL(str(resource_path('native/sector_retime.dll')))
    for name in ('retime_sectors','verify_sectors'):
        f=getattr(lib,name);f.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint];f.restype=ctypes.c_int
    return lib

def repack_common(image,replacement,track5,track3,packing_mode='common_uncompressed'):
    """Grow COMMON in copies; alias equal MPB files and shift intervening extents."""
    track5,track3=Path(track5),Path(track3)
    if track5.resolve()==image.track5.resolve() or track3.resolve()==image.track3.resolve():
        raise ValueError('Refusing to modify original tracks')
    entries={e.name:e for e in image.entries()}
    common=entries['COMMON_DATA.PVM']; donor=entries['R22.MPB']; shared=entries['R21.MPB']
    raw=Path(replacement).read_bytes()
    growth=(len(raw)+2047)//2048-(common.size+2047)//2048
    if not 0<growth<(donor.size+2047)//2048:
        raise ValueError('COMMON growth exceeds verified shared-audio space')
    shifted=sorted([e for e in entries.values() if common.lba<e.lba<donor.lba],key=lambda e:e.lba)
    if shifted[-1].lba+(shifted[-1].size+2047)//2048+growth>donor.lba+(donor.size+2047)//2048:
        raise ValueError('Relocated files exceed the shared audio extent')
    if not track3.exists():
        import shutil
        shutil.copyfile(image.track3,track3)
    with GDImage(image.cue_dir,track3=track3,track5=track5) as current:
        if current.read(donor.lba,donor.size)!=current.read(shared.lba,shared.size):
            raise ValueError('The two audio files are not byte-identical')
        shared_hash=hashlib.sha256(current.read(shared.lba,shared.size)).hexdigest()
    lib=_codec(); proof=[]
    with track5.open('r+b') as stream:
        # Copy backwards: positive shifts may overlap their source extents.
        for entry in reversed(shifted):
            count=(entry.size+2047)//2048
            stream.seek((entry.lba-image.track5_start)*SECTOR)
            data=bytearray(stream.read(count*SECTOR))
            before=np.frombuffer(data,np.uint8).reshape(count,SECTOR)[:,16:2064].copy().tobytes()[:entry.size]
            ptr=(ctypes.c_ubyte*len(data)).from_buffer(data)
            assert lib.retime_sectors(ptr,count,entry.lba+growth)==0
            assert lib.verify_sectors(ptr,count,entry.lba+growth)==0
            after=np.frombuffer(data,np.uint8).reshape(count,SECTOR)[:,16:2064].copy().tobytes()[:entry.size]
            assert before==after
            stream.seek((entry.lba+growth-image.track5_start)*SECTOR);stream.write(data)
            proof.append({'name':entry.name,'old_lba':entry.lba,'new_lba':entry.lba+growth,
                          'size':entry.size,'sha256':hashlib.sha256(before).hexdigest(),'valid_sectors':count})
        count=(len(raw)+2047)//2048
        data=bytearray(count*SECTOR)
        for n in range(count):
            stream.seek((common.lba+n-image.track5_start)*SECTOR)
            template=stream.read(SECTOR)
            data[n*SECTOR:(n+1)*SECTOR]=update_mode1(template,raw[n*2048:(n+1)*2048].ljust(2048,b'\0'))
        ptr=(ctypes.c_ubyte*len(data)).from_buffer(data)
        assert lib.retime_sectors(ptr,count,common.lba)==0
        assert lib.verify_sectors(ptr,count,common.lba)==0
        stream.seek((common.lba-image.track5_start)*SECTOR);stream.write(data)
    changes={e.name:(e.lba+growth,e.size) for e in shifted}
    changes[common.name]=(common.lba,len(raw));changes[donor.name]=(shared.lba+growth,shared.size)
    with GDImage(image.cue_dir,track3=track3,track5=track5) as current:
        directory=bytearray(current.read(image.root_lba,image.root_size))
    offset=0;dirty=set();matched=set()
    while offset<len(directory):
        length=directory[offset]
        if not length:
            offset=(offset//2048+1)*2048;continue
        name=bytes(directory[offset+33:offset+33+directory[offset+32]]).split(b';')[0].decode('ascii','replace')
        if name in changes:
            lba,size=changes[name]
            for pos,value in ((2,lba),(10,size)):
                struct.pack_into('<I',directory,offset+pos,value)
                struct.pack_into('>I',directory,offset+pos+4,value)
            dirty.add(offset//2048);matched.add(name)
        offset+=length
    assert matched==set(changes)
    with track3.open('r+b') as stream:
        for sector in sorted(dirty):
            index=image.root_lba+sector-image.volume_start
            stream.seek(index*SECTOR);old=stream.read(SECTOR)
            data=update_mode1(old,directory[sector*2048:(sector+1)*2048].ljust(2048,b'\0'))
            assert verify_mode1(data)
            stream.seek(index*SECTOR);stream.write(data)
    report={'packing_mode':packing_mode,'growth_sectors':growth,
            'common_size':len(raw),'shared_audio_files':[shared.name,donor.name],
            'shared_audio_sha256':shared_hash,'audio_bytes_preserved':True,
            'shifted_files':proof,'root_directory_sectors':len(dirty),
            'disc_geometry_unchanged':True,'original_disc_modified':False}
    return report
