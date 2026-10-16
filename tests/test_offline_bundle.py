"""Reject damaged or augmented executable deployment bundles before building."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('verify_offline_bundle', Path(__file__).resolve().parents[1] / 'scripts/verify_offline_bundle.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / 'bundle'
    (root / 'app').mkdir(parents=True)
    body = b'print("synthetic")\n'
    (root / 'app/app.py').write_bytes(body)
    manifest = {'format': 1, 'platform': 'linux/amd64', 'image': 'plw:0.3.1-offline-1234567',
        'source_commit': '1' * 40, 'files': [{'path': 'app/app.py', 'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()}]}
    (root / 'bundle-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return root, manifest


def test_complete_bundle_is_verified(bundle):
    root, _ = bundle
    assert verifier.verify(root)['valid']


def test_equal_size_tamper_is_rejected(bundle):
    root, _ = bundle
    target = root / 'app/app.py'
    target.write_bytes(target.read_bytes().replace(b'print', b'INPUT'))
    with pytest.raises(ValueError, match='checksum'):
        verifier.verify(root)


def test_extra_python_file_is_rejected(bundle):
    root, _ = bundle
    (root / 'app/extra.py').write_text('synthetic', encoding='utf-8')
    with pytest.raises(ValueError, match='Unexpected'):
        verifier.verify(root)


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'app/../outside', 'app\\app.py', 'app/a:stream'])
def test_traversal_or_ambiguous_paths_rejected(bundle, name):
    root, manifest = bundle
    manifest['files'][0]['path'] = name
    (root / 'bundle-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Unsafe'):
        verifier.verify(root)


def test_duplicate_manifest_record_rejected(bundle):
    root, manifest = bundle
    manifest['files'].append(manifest['files'][0])
    (root / 'bundle-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate'):
        verifier.verify(root)


def test_missing_file_rejected(bundle):
    root, manifest = bundle
    manifest['files'][0]['path'] = 'app/missing.py'
    (root / 'bundle-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(FileNotFoundError):
        verifier.verify(root)
