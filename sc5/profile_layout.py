"""Fit the existing Korean profile category artwork to its native sprites."""
from __future__ import annotations

import struct
import json
from PIL import Image

BASE = 0x8c010000
CATEGORY_DESCRIPTORS = [0x8c03a084 + 40 * i for i in range(6)]


def patch_profile_layout(original, patched, project):
    item_id = 'TITLE.PVM:090'
    record = project.edits('images').get(item_id, {})
    if record.get('status') != 'edited':
        return []
    labels = record['labels']
    if len(labels) != len(CATEGORY_DESCRIPTORS):
        raise ValueError('Expected six profile category labels')
    image = Image.open(project.replacement('images', item_id)).convert('RGBA')
    repairs = []
    for address, label in zip(CATEGORY_DESCRIPTORS, labels):
        offset = address - BASE
        old = struct.unpack_from('<IHH8f', original, offset)
        assert old[:3] == (5090, 256, 256)
        x, y, w, h = label['region']
        box = image.crop((x, y, x + w, y + h)).getchannel('A').getbbox()
        if not box:
            raise ValueError('Empty profile category artwork')
        left, top, right, bottom = box
        # Keep a transparent sampling border on every side. Even dimensions
        # keep a centered sprite on whole screen pixels, avoiding half-pixel
        # filtering of the original sharp artwork.
        left += x - 2; right += x + 2
        top += y - 2; bottom += y + 2
        right += (right - left) % 2
        bottom += (bottom - top) % 2
        assert 0 <= left < right <= image.width and 0 <= top < bottom <= image.height
        expected = (x + box[0] - left, y + box[1] - top,
                    x + box[2] - left, y + box[3] - top)
        assert image.crop((left, top, right, bottom)).getchannel('A').getbbox() == expected
        values = list(old)
        values[3:7] = [left / 256, top / 256, right / 256, bottom / 256]
        values[7:11] = [.5, .5, 1., 1.]
        struct.pack_into('<IHH8f', patched, offset, *values)
        repairs.append({'asset': 'Profile category', 'korean': label['korean'],
                        'address': hex(address), 'old_uv_pixels': [v * 256 for v in old[3:7]],
                        'uv_pixels': [left, top, right, bottom], 'centered': True,
                        'artwork_pixels_changed': False})
    policy = json.loads((project.data / 'font_policy.json').read_text('utf-8'))
    if policy['cpro_layout'].get('native_body_pixel_grid'):
        address = 0x8c039f54
        offset = address - BASE
        old = struct.unpack_from('<IHH8f', original, offset)
        assert old[:3] == (70000, 512, 512)
        assert old[3:7] == (0., 26 / 512, 400 / 512, 1.)
        assert abs(old[10] - .88) < .00001
        values = list(old)
        values[6] = 210 / 512
        values[10] = 1.
        struct.pack_into('<IHH8f', patched, offset, *values)
        repairs.append({'asset': 'Profile body', 'address': hex(address),
                        'old_scale': list(old[9:11]), 'new_scale': [1, 1],
                        'line_spacing': 23, 'uv_pixels': [0, 26, 400, 210],
                        'thin_horizontal_strokes_preserved': True})
    return repairs
