"""Verify a loaded base image with either classic or containerd image identities."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

TAG = 'python:3.14-slim-bookworm'


def imported_manifest_digest(config_digest, config_size, layers):
    value = dict(schemaVersion=2, mediaType='application/vnd.docker.distribution.manifest.v2+json',
        config=dict(mediaType='application/vnd.docker.container.image.v1+json', digest=config_digest, size=config_size),
        layers=[dict(mediaType='application/vnd.docker.image.rootfs.diff.tar', digest=digest, size=size)
                for digest, size in layers])
    return 'sha256:' + hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def archive_identity(root):
    root = Path(root)
    provenance = json.loads((root / 'base-image-provenance.json').read_text(encoding='utf-8'))
    path = root / 'python-3.14-slim-bookworm-amd64.tar.gz'
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != provenance['archive_sha256']:
            raise ValueError('Base archive checksum mismatch')
    with tarfile.open(path, 'r:gz') as archive:
        records = json.load(archive.extractfile('manifest.json'))
        if len(records) != 1 or records[0]['RepoTags'] != [TAG]:
            raise ValueError('Unexpected archive image/tag')
        record = records[0]
        with archive.extractfile(record['Config']) as stream:
            raw = stream.read(1024 * 1024 + 1)
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        if len(raw) > 1024 * 1024 or digest != provenance['config_digest']:
            raise ValueError('Base config digest mismatch')
        config = json.loads(raw)
        if config.get('os') != 'linux' or config.get('architecture') != 'amd64':
            raise ValueError('Unexpected archive platform')
        diff_ids = config['rootfs']['diff_ids']
        if diff_ids != provenance['diff_ids'] or len(record['Layers']) != len(diff_ids):
            raise ValueError('Base layer sequence mismatch')
        layers = []
        for name, expected in zip(record['Layers'], diff_ids):
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError('Base layer must be a regular archive member')
            with archive.extractfile(member) as stream:
                actual = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected:
                raise ValueError('Base layer digest mismatch')
            layers.append((actual, member.size))
    return dict(config_digest=digest, imported_digest=imported_manifest_digest(digest, len(raw), layers),
                diff_ids=diff_ids, os='linux', architecture='amd64')


def check_inspection(info, expected):
    if (info.get('Os') != expected['os'] or info.get('Architecture') != expected['architecture']
            or info.get('RootFS', {}).get('Layers') != expected['diff_ids']):
        raise ValueError('Loaded image platform or layers mismatch')
    identity = info.get('Id')
    if identity not in (expected['config_digest'], expected['imported_digest']):
        raise ValueError('Loaded image identity mismatch')
    if identity == expected['imported_digest'] and info.get('Descriptor', {}).get('digest') != identity:
        raise ValueError('Loaded image descriptor mismatch')
    return dict(valid=True, identity=identity, identity_type='config' if identity == expected['config_digest'] else 'imported-manifest',
                layers=len(expected['diff_ids']), platform='linux/amd64')


def verify(root):
    expected = archive_identity(root)
    info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', TAG], text=True))[0]
    return check_inspection(info, expected)


if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1])))
