"""Explicit Windows/Linux profile. No learning data is created by configuration."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .private_auth import validate_hash


def load_profile(filename,*,preview=False):
    source=Path(filename)
    if not source.is_absolute() or source.is_symlink() or source.stat().st_nlink!=1 or source.stat().st_size>16384:
        raise ValueError('配置需要小于 16 KB 的独立本机文件。')
    value=json.loads(source.read_text(encoding='utf-8'))
    if set(value)!={'origin','username','password_digest','data_root','backup_root','pdf_python','port'}:
        raise ValueError('私人网站配置字段不完整或包含未知字段。')
    origin=urlsplit(value['origin'])
    if (origin.path or origin.query or origin.fragment or origin.username or origin.password or not origin.hostname
        or origin.scheme!='https' and not (preview and origin.scheme=='http' and origin.hostname=='127.0.0.1')):
        raise ValueError('正式地址必须为 HTTPS 根地址；本机预览只允许 127.0.0.1。')
    validate_hash(value['password_digest'])
    if not isinstance(value['username'],str) or not 1<=len(value['username'])<=80:raise ValueError('账号无效。')
    if type(value['port']) is not int or not 1024<=value['port']<=65535:raise ValueError('端口无效。')
    project=Path(__file__).resolve().parents[2]
    roots=[Path(value[k]) for k in ('data_root','backup_root')]
    for root in roots:
        if not root.is_absolute() or (os.name == 'nt' and (len(root.drive)!=2 or root.drive[1]!=':')) or '..' in root.parts:raise ValueError('数据目录需要当前系统的本机绝对路径。')
        if root==Path(root.anchor):raise ValueError('数据目录不能是磁盘根目录。')
        if any(item.is_symlink() or item.is_junction() for item in (root,*root.parents)):raise ValueError('数据目录不能包含链接。')
        if root.is_relative_to(project) and not (preview and root.is_relative_to(project/'.sandbox/test-runs')):
            raise ValueError('学习数据须与代码目录分离。')
    if roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):raise ValueError('数据和备份目录不能互相包含。')
    if preview and not all(root.is_relative_to(project/'.sandbox/test-runs') for root in roots):
        raise ValueError('本机网站预览只能使用独立的合成学习库。')
    if any(source.is_relative_to(root) for root in roots):raise ValueError('登录配置须独立于学习库与备份目录。')
    if any(item.is_symlink() or item.is_junction() for item in (source,*source.parents)):
        raise ValueError('登录配置不能包含链接。')
    python=Path(value['pdf_python'])
    if not python.is_absolute() or not python.is_file():raise ValueError('请配置含 pypdf 的专用 Python。')
    return value


def configure_profile(profile):
    os.environ.update(PLW_PRIVATE_SITE='1',PLW_DATA_ROOT=profile['data_root'],
        PLW_BACKUP_ROOT=profile['backup_root'],PLW_WORKSPACE=profile['data_root'],PLW_PDF_PYTHON=profile['pdf_python'])
