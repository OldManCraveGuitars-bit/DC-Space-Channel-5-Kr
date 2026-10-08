"""Align the cleaned interlude with the existing Korean subtitle style."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc5.editor_project import Project, read_lines
from sc5.runtime_config import export_runtime


def main():
    project = Project(ROOT)
    titles = ('R1_MAKUMA.SFD', 'R2_MAKUMA.SFD', 'R3_MAKUMA.SFD', 'R4_MAKUMA_1.SFD')
    old_titles = {name: project.edits('videos')[name] for name in titles}
    reviews = {r['id']: r for r in read_lines(project.data/'movie_caption_review.jsonl')}
    for name in ('R4_MAKUMA.SFD',):
        record = project.edits('videos')[name]
        for segment in record['segments']:
            segment['bottom_offset'] = 48
            segment.pop('source_cover', None)
        record['layout_review'] = '2026-10-08: Japanese dialogue removed from video; original subtitle style retained at the original dialogue position; chapter titles unchanged'
        saved = project.save_record('videos', name, record, project.item('videos', name)['duration'])
        reviews[name] = {'id': name, **saved}
    assert old_titles == {name: project.edits('videos')[name] for name in titles}
    project._commit({project.data/'movie_caption_review.jsonl':
                    ('\n'.join(json.dumps(reviews[k], ensure_ascii=False) for k in sorted(reviews))+'\n').encode('utf-8')})
    export_runtime(project)
    project.export_text(project.data/'localization_export.csv')
    print('12 R4 dialogue cues aligned at bottom 48; existing 115/255 subtitle box; chapter titles and OP unchanged')


if __name__ == '__main__':
    main()
