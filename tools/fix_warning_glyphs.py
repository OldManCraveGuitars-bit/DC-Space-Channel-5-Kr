"""Smooth save/load warning glyphs without increasing the original VQ allocation."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc5.editor_project import Project, read_lines
from sc5.assets import encode_vq_regions, decode_pvr
from PIL import Image


def main():
    project = Project(ROOT)
    item_id = 'COMMON_DATA.PVM:291'
    old = project.edits('images')[item_id]
    groups = {}
    for label in old['labels']:
        groups.setdefault(label['message_key'], []).append(label)
    labels = []
    for rows in groups.values():
        start_y = rows[0]['row'] * 26
        size = 16 if rows[0]['message_key'] in {'overwrite_or_continue', 'power_warning'} else 18 if rows[0]['message_key'] == 'controller_or_vmu_busy' else 22
        line_spacing = size + 4
        for index, label in enumerate(rows):
            source = [label['source_x'], label['row'] * 26, label.get('source_region', label['region'])[2], 26]
            labels.append(dict(label, source_region=source, source_y=source[1],
                region=[0, start_y + index * line_spacing, source[2], line_spacing],
                font_size=size, baseline=size if size < 22 else 20,
                spacing_candidates=[size + 2, size + 1, size], latin_scale=size/26,
                native_pixel_size=True,
                glyph_rasterization='coverage_crisp', glyph_stroke_quarters=0))
    regions = [label['source_region'] for label in labels] + [label['region'] for label in labels]
    saved = project.save_record('images', item_id, old | {
        'labels': labels, 'edit_regions': regions, 'text_matches_image': False,
        'note': 'Save/load warning: Yeongdeok Blueroad rasterized at screen size (overwrite: 16px, 20px line spacing), 4x area coverage. No stroke expansion, ringing or fractional downscale. English wording preserved; A/B/5 shapes sampled from the source. Exact VQ fit without extra texture memory.'})
    item = project.item('images', item_id)
    source = project.disc_bytes(item['archive'], item['offset'], item['size'])
    edited = Image.open(project.replacement('images', item_id)).convert('RGBA')
    packed, audit = encode_vq_regions(source, edited, saved['edit_regions'])
    assert len(packed) == len(source)
    assert audit['outside_regions_exact'] and audit['premultiplied_rmse'] == 0
    out = ROOT / 'work/save-boss-review-20261007'
    out.mkdir(parents=True, exist_ok=True)
    decode_pvr(packed).save(out / 'warning-smooth-packed.png')
    (out / 'warning-smoothing-verification.json').write_text(json.dumps(audit | {
        'item': item_id, 'length_unchanged': True, 'font': str(project.font),
        'font_size_by_message': {key: next(label['font_size'] for label in labels if label['message_key'] == key) for key in groups},
        'overwrite_font_size': 16, 'overwrite_line_spacing': 20, 'display_scale': 1,
        'original_english_wording_preserved': True,
        'glyph_rasterization': 'coverage_crisp', 'glyph_stroke_quarters': 0}, indent=2) + '\n', 'utf-8')
    reviews = read_lines(project.data / 'image_text_review.jsonl')
    for review in reviews:
        if review['id'] == item_id:
            label = next(label for label in labels if label['row'] == review['row'])
            review['glyph_rasterization'] = 'coverage_crisp'
            review['glyph_stroke_quarters'] = 0
            review.update({key: label[key] for key in ('region', 'source_region', 'source_y', 'font_size', 'baseline', 'spacing_candidates', 'latin_scale', 'native_pixel_size')})
            review['line_spacing'] = label['region'][3]
    project._commit({project.data / 'image_text_review.jsonl':
        ('\n'.join(json.dumps(row, ensure_ascii=False) for row in reviews) + '\n').encode('utf-8')})
    project.export_text(project.data / 'localization_export.csv')
    print(json.dumps(audit))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
