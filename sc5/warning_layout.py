"""Display save/load notices at their rasterized pixel size on the console."""
from __future__ import annotations

import struct
from PIL import Image

BASE = 0x8c010000
DESCRIPTORS = [
    (0x8c036f88, 'controller_or_vmu_busy'),
    (0x8c036fb0, 'vmu_space_required'),
    (0x8c036fd8, 'overwrite_or_continue'),
    (0x8c037000, 'load_failed'),
    (0x8c037028, 'file_unusable'),
    (0x8c037050, 'save_failed'),
    (0x8c037078, 'no_save_file'),
    (0x8c0370a0, 'power_warning'),
]


def patch_warning_layout(original, patched, project):
    record = project.edits('images')['COMMON_DATA.PVM:291']
    # Older projects retain their original texture geometry.
    if not all(label.get('native_pixel_size') for label in record['labels']):
        return []
    image = Image.open(project.replacement('images', 'COMMON_DATA.PVM:291')).convert('RGBA')
    repairs = []
    for address, key in DESCRIPTORS:
        offset = address - BASE
        old = struct.unpack_from('<IHH8f', original, offset)
        assert old[:3] == (292, 512, 512)
        rows = [label for label in record['labels'] if label['message_key'] == key]
        y = min(label['region'][1] for label in rows)
        height = max(label['region'][1] + label['region'][3] for label in rows) - y
        bounds = image.crop((0, y, 512, y + height)).getchannel('A').getbbox()
        assert bounds
        width = (bounds[2] + 3) & ~1
        assert width <= 494 and height <= 78
        values = list(old)
        values[3:7] = [0, y / 512, width / 512, (y + height) / 512]
        values[9:11] = [1, 1]
        struct.pack_into('<IHH8f', patched, offset, *values)
        repairs.append({'asset': 'Save/load warning', 'message': key, 'address': hex(address),
            'old_scale': list(old[9:11]), 'new_scale': [1, 1], 'uv_pixels': [0, y, width, height],
            'font_size': rows[0]['font_size'], 'line_spacing': rows[0]['region'][3]})
    return repairs
