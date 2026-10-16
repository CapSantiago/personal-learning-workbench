"""Extract four known files from a verified official static package, no tar paths used."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile


def extract(root, destination):
    root, destination = Path(root), Path(destination)
    if not root.is_absolute() or not destination.is_absolute() or not destination.is_dir():
        raise ValueError('Use absolute existing paths')
    for path in (root, destination):
        if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError('Linked paths are not supported')
    record = json.loads((root / 'tailscale-provenance.json').read_text(encoding='utf-8'))
    name = record['filename']
    if not re.fullmatch(r'tailscale_[0-9.]+_amd64.tgz', name):
        raise ValueError('Unexpected Tailscale archive')
    source = root / name
    if source.is_symlink() or source.stat().st_nlink != 1:
        raise ValueError('Package must be an independent file')
    with source.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
            raise ValueError('Tailscale archive checksum mismatch')
    prefix = name.removesuffix('.tgz')
    members = {prefix + '/tailscale': 'tailscale', prefix + '/tailscaled': 'tailscaled',
               prefix + '/systemd/tailscaled.service': 'tailscaled.service',
               prefix + '/systemd/tailscaled.defaults': 'tailscaled.defaults'}
    with tarfile.open(source, 'r:gz') as archive:
        for old, new in members.items():
            found = [item for item in archive.getmembers() if item.name == old]
            if len(found) != 1 or not found[0].isfile() or not 0 < found[0].size < 128 * 1024**2:
                raise ValueError('Unexpected package member: ' + old)
            with archive.extractfile(found[0]) as input_file, (destination / new).open('xb') as output:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
    return {'extracted': sorted(members.values()), 'version': record['version']}


if __name__ == '__main__':
    print(json.dumps(extract(sys.argv[1], sys.argv[2])))
