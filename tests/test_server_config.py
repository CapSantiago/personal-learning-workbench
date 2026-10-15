import json
from pathlib import Path
from uuid import uuid4

import pytest

from plw import storage
from plw.private_auth import password_hash
from plw.server_config import load_profile


@pytest.fixture
def profile():
    root=storage.ROOTS[1]/('server-config-'+str(uuid4()));root.mkdir()
    value=dict(origin='http://127.0.0.1:8515',username='student',password_digest=password_hash('Synthetic-password-2026'),
        data_root=str(root/'data'),backup_root=str(root/'backups'),pdf_python=str(storage.PROJECT_ROOT/'.venv/Scripts/python.exe'),port=8515)
    return root,value


def save(root,value):
    file=root/'site.json';file.write_text(json.dumps(value),encoding='utf-8');return file


def test_preview_config_does_not_create_data(profile):
    root,value=profile
    assert load_profile(save(root,value),preview=True)==value
    assert not Path(value['data_root']).exists()


@pytest.mark.parametrize('key,value',[('origin','http://example.test'),('origin','https://study.example.test/path'),
    ('origin','https://name:secret@example.test'),('port',80),('data_root','E:/'),('data_root','E:/PLW-Data'),
    ('username',''),('password_digest','plain-text-password')])
def test_invalid_preview_fails_closed(profile,key,value):
    root,config=profile;config[key]=value
    with pytest.raises(ValueError):load_profile(save(root,config),preview=True)


def test_formal_profile_refuses_http_and_nested_backups(profile):
    root,value=profile
    with pytest.raises(ValueError,match='HTTPS'):load_profile(save(root,value))
    value['backup_root']=str(Path(value['data_root'])/'backups')
    with pytest.raises(ValueError,match='包含'):load_profile(save(root,value),preview=True)
