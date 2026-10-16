"""Verify an offline release before loading images or executing builds (stdlib only)."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


def verify(root):
    root = Path(root)
    if not root.is_absolute() or any(p.is_symlink() or p.is_junction() for p in (root, *root.parents)):
        raise ValueError('Use an absolute bundle directory without links')
    manifest_path = root / 'bundle-manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_nlink != 1:
        raise ValueError('Manifest must be an independent regular file')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['format'] != 1 or manifest['platform'] != 'linux/amd64':
        raise ValueError('Unexpected bundle format/platform')
    seen = set()
    for record in manifest['files']:
        name = record['path']
        relative = PurePosixPath(name)
        if (not isinstance(name, str) or relative.is_absolute() or '..' in relative.parts
                or relative.as_posix() != name or '\\' in name or ':' in name or name in seen
                or name in ('', '.', 'bundle-manifest.json')):
            raise ValueError('Unsafe or duplicate manifest path')
        seen.add(name)
        path = root.joinpath(*relative.parts)
        if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError('Linked bundle files are not permitted')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != record['size']:
            raise ValueError('Bundle file size/type mismatch: ' + name)
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != record['sha256']:
            raise ValueError('Bundle checksum mismatch: ' + name)
    actual_names = set()
    for path in root.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('Bundle contains a link')
        if path.is_file():
            actual_names.add(path.relative_to(root).as_posix())
    if actual_names != seen | {'bundle-manifest.json'}:
        raise ValueError('Unexpected or missing bundle files')
    return {'valid': True, 'files': len(seen), 'platform': manifest['platform'],
            'image': manifest['image'], 'source_commit': manifest['source_commit']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    print(json.dumps(verify(parser.parse_args().root), ensure_ascii=False))
