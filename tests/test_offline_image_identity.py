"""Regression for the actual Docker 29 manifest reported during first deployment."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_loaded_image', ROOT / 'scripts/verify_loaded_image.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
sys.modules['verify_loaded_image'] = identity
resume_spec = importlib.util.spec_from_file_location('resume_offline_prepare', ROOT / 'scripts/resume_offline_prepare.py')
resume = importlib.util.module_from_spec(resume_spec)
resume_spec.loader.exec_module(resume)

CONFIG = 'sha256:82cd6bca489be723b62b192752c133eb7c6acbcecaeca797628725d994998c5b'
IMPORTED = 'sha256:86dec9b258fdaaf77fe397b059e1ad87210afcdfca5a028c9d795c6b65d0d1ba'
LAYERS = [
    ('sha256:e58989146fcec76699871403b9897b5c014af1ccd85f5a9300a215e7975525d7', 77936640),
    ('sha256:08e075203608b4f8b242d98f108e01db067b23db2f0f1a611b02ab462250b89a', 8852992),
    ('sha256:9a6dbecf1dd0bbab6f8dc7951f40fe1814eda6180322e47f2bd0bc5c798eb682', 47577600),
    ('sha256:020f37c339b9fc549a11bcc5a937b81e3500281270bb62edde29022b27919d86', 5120),
]
EXPECTED = dict(config_digest=CONFIG, imported_digest=IMPORTED, diff_ids=[d for d, _ in LAYERS], os='linux', architecture='amd64')
OBSERVED = dict(Id=IMPORTED, Os='linux', Architecture='amd64', RootFS=dict(Layers=EXPECTED['diff_ids']), Descriptor=dict(digest=IMPORTED))


def test_actual_docker29_digest_is_reconstructed_exactly():
    assert identity.imported_manifest_digest(CONFIG, 4961, LAYERS) == IMPORTED
    assert identity.check_inspection(OBSERVED, EXPECTED)['identity_type'] == 'imported-manifest'


def test_classic_config_identity_still_supported():
    old = copy.deepcopy(OBSERVED)
    old['Id'] = CONFIG
    old.pop('Descriptor')
    assert identity.check_inspection(old, EXPECTED)['identity_type'] == 'config'


@pytest.mark.parametrize('field', ['identity', 'layer', 'platform', 'descriptor'])
def test_mismatches_are_not_accepted(field):
    changed = copy.deepcopy(OBSERVED)
    if field == 'identity':
        changed['Id'] = 'sha256:' + '0' * 64
    elif field == 'layer':
        changed['RootFS']['Layers'][0] = 'sha256:' + '0' * 64
    elif field == 'platform':
        changed['Architecture'] = 'arm64'
    else:
        changed['Descriptor']['digest'] = CONFIG
    with pytest.raises(ValueError):
        identity.check_inspection(changed, EXPECTED)


def test_archive_identity_verifies_config_and_layer_contents(tmp_path):
    body = b'synthetic layer bytes'
    diff = 'sha256:' + hashlib.sha256(body).hexdigest()
    config = json.dumps(dict(os='linux', architecture='amd64', rootfs=dict(diff_ids=[diff]))).encode()
    digest = 'sha256:' + hashlib.sha256(config).hexdigest()
    path = tmp_path / 'python-3.14-slim-bookworm-amd64.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in [('config.json', config), ('layer.tar', body), ('manifest.json', json.dumps([dict(Config='config.json', RepoTags=[identity.TAG], Layers=['layer.tar'])]).encode())]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    provenance = dict(archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), config_digest=digest, diff_ids=[diff])
    (tmp_path / 'base-image-provenance.json').write_text(json.dumps(provenance), encoding='utf-8')
    actual = identity.archive_identity(tmp_path)
    assert actual['config_digest'] == digest
    assert actual['imported_digest'] == identity.imported_manifest_digest(digest, len(config), [(diff, len(body))])
    provenance['config_digest'] = CONFIG
    (tmp_path / 'base-image-provenance.json').write_text(json.dumps(provenance), encoding='utf-8')
    with pytest.raises(ValueError, match='config digest'):
        identity.archive_identity(tmp_path)


def test_resume_preserves_original_installer_and_replaces_only_identity_check(tmp_path):
    original = '#!/bin/bash\nset -e\nROOT="old"\ncase "$1" in\nprepare)\n'
    original += '    [[ "actual" == "$expected" ]] || fail \'Loaded base image identity mismatch.\'\n'
    original += '    echo next-step\n;;\nesac\n'
    target = tmp_path / 'install_offline.sh'
    target.write_text(original, encoding='utf-8')
    generated = resume.patched_script(tmp_path, tmp_path / 'helper with spaces.py')
    assert target.read_text(encoding='utf-8') == original
    assert 'echo next-step' in generated and 'Loaded base image identity mismatch' not in generated
    assert 'helper with spaces.py' in generated and '"$ROOT"' in generated


def test_resume_rejects_an_unexpected_installer(tmp_path):
    (tmp_path / 'install_offline.sh').write_text('ROOT=old\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Unexpected installer'):
        resume.patched_script(tmp_path, tmp_path / 'helper.py')
