"""Verified same-allocation movie replacements; original disc stays read-only."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def _project_path(project, relative):
    path = (project.root / relative).resolve()
    if not path.is_relative_to(project.root.resolve()):
        raise ValueError('Movie replacement outside project')
    return path


def _restore_movie(project, row):
    """Public packages carry only a delta; reconstruct from the user's disc."""
    patch = _project_path(project, row['patch'])
    if hashlib.sha256(patch.read_bytes()).hexdigest() != row['patch_sha256']:
        raise ValueError('Movie delta checksum mismatch')
    tool = _project_path(project, row['patch_tool'])
    if hashlib.sha256(tool.read_bytes()).hexdigest() != row['patch_tool_sha256']:
        raise ValueError('Movie delta tool checksum mismatch')
    cache = project.root / 'work/movie-replacements'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (row['sha256'] + '.sfd')
    if target.is_file():
        return target
    original = project.disc_bytes(row['name'], 0, row['original_size'])
    if hashlib.sha256(original).hexdigest() != row['original_sha256']:
        raise ValueError('Movie source differs from the supported Japanese disc')
    with tempfile.TemporaryDirectory(dir=cache) as directory:
        source = Path(directory) / 'original.sfd'
        output = Path(directory) / 'patched.sfd'
        source.write_bytes(original)
        subprocess.run([str(tool), '-d', '-s', str(source), str(patch), str(output)],
                       check=True, capture_output=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        blob = output.read_bytes()
        if len(blob) != row['original_size'] or hashlib.sha256(blob).hexdigest() != row['sha256']:
            raise ValueError('Reconstructed movie checksum mismatch')
        output.replace(target)
    return target


def registered_movies(project):
    manifest = project.data/'movie_replacements.json'
    if not manifest.exists():
        return {}, []
    rows = json.loads(manifest.read_text('utf-8'))['movies']
    paths = {}
    for row in rows:
        path = _project_path(project, row['path'])
        if not path.is_file() and row.get('patch'):
            path = _restore_movie(project, row)
        blob = path.read_bytes()
        if len(blob) != row['original_size'] or hashlib.sha256(blob).hexdigest() != row['sha256']:
            raise ValueError(f"Movie replacement changed: {row['name']}")
        paths[row['name']] = path
    return paths, rows
