"""Conservative Windows file operations, restricted to synthetic PLW data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOTS = (PROJECT_ROOT / '.sandbox' / 'm2', PROJECT_ROOT / '.sandbox' / 'test-runs')
PRODUCTION_ROOT = Path(os.environ.get('PLW_DATA_ROOT','E:/PLW-Data' if os.name == 'nt' else '/var/lib/plw/data'))
BACKUP_ROOT = Path(os.environ.get('PLW_BACKUP_ROOT','E:/PLW-Backups' if os.name == 'nt' else '/var/lib/plw/backups'))
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


class StorageError(RuntimeError):
    pass


def safe_path(path, root=None, must_exist=False, directory=None, *, source_only=False) -> Path:
    path = Path(path)
    if not path.is_absolute() or (os.name == 'nt' and (len(path.drive) != 2 or path.drive[1] != ':')) or '..' in path.parts:
        raise StorageError('仅支持无上级跳转的本机绝对路径。')
    if not source_only and not any(path.is_relative_to(scope) for scope in (*ROOTS, PRODUCTION_ROOT, BACKUP_ROOT)):
        raise StorageError('当前仅允许 M2 或 test-runs 合成目录。')
    if root is not None and not path.is_relative_to(Path(root)):
        raise StorageError('路径越出指定根目录。')
    for part in path.parts[1:]:
        if (not part or part.endswith((' ', '.')) or any(c in part for c in '<>:"|?*')
                or any(ord(c) < 32 for c in part) or part.split('.')[0].upper() in RESERVED):
            raise StorageError('不支持歧义文件名、设备名或备用数据流。')
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise StorageError('不支持符号链接、目录联接或重解析点。')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise StorageError('不支持具有额外硬链接的文件。')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise StorageError('路径的父级必须是目录。')
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    if path.exists():
        if directory is True and not path.is_dir():
            raise StorageError('需要目录。')
        if directory is False and not path.is_file():
            raise StorageError('需要普通文件。')
    return path


def check_source(path, must_exist=False, *, db_path=None) -> Path:
    production = db_path is not None and Path(db_path).is_relative_to(PRODUCTION_ROOT)
    path = safe_path(path, must_exist=must_exist, directory=False, source_only=production)
    if production:
        if any(path.is_relative_to(p) for p in (PRODUCTION_ROOT, BACKUP_ROOT, PROJECT_ROOT)):
            raise StorageError('请选择原始学习资料，不要导入 PLW 内部文件或备份。')
        return path
    samples = ROOTS[0] / 'sources'
    in_test_sources = path.is_relative_to(ROOTS[1]) and 'sources' in path.relative_to(ROOTS[1]).parts[:-1]
    if not path.is_relative_to(samples) and not in_test_sources:
        raise StorageError('来源只能是专门的合成目录 sources，不能导入真实资料或内部文件。')
    return path


def relative_file(root, rel, must_exist=False) -> Path:
    if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel:
        raise StorageError('需要规范的内部相对路径。')
    parts = rel.split('/')
    if any(x in ('', '.', '..') for x in parts) or PurePosixPath(rel).is_absolute():
        raise StorageError('相对路径包含跳转或歧义。')
    return safe_path(Path(root).joinpath(*parts), root=root, must_exist=must_exist, directory=False)


def hash_file(path) -> tuple[int, str]:
    path = safe_path(path, must_exist=True, directory=False, source_only=True)
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as source:
        before = os.fstat(source.fileno())
        if before.st_nlink != 1:
            raise StorageError('打开的文件有额外硬链接。')
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(source.fileno())
    safe_path(path, must_exist=True, directory=False, source_only=True)
    current = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns) or (after.st_ino, after.st_size, after.st_mtime_ns) != (current.st_ino, current.st_size, current.st_mtime_ns):
        raise StorageError('读取期间文件发生变化，请重新检查。')
    return size, digest.hexdigest()


def copy_verified(source, target, expected_sha256=None) -> tuple[int, str]:
    source = safe_path(source, must_exist=True, directory=False, source_only=True)
    target = safe_path(target, directory=False)
    if source == target or target.exists():
        raise StorageError('复制目标必须是尚不存在的新文件。')
    expected_size, expected_hash = hash_file(source)
    if expected_sha256 is not None and expected_hash != expected_sha256:
        raise StorageError('源文件与已记录校验值不一致。')
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(target, directory=False)
    with source.open('rb') as reader, target.open('xb') as writer:
        while chunk := reader.read(1024 * 1024):
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    result = hash_file(target)
    if result != (expected_size, expected_hash) or hash_file(source) != result:
        raise StorageError('复制期间内容发生变化，保留未完成文件供检查。')
    return result


def read_json(path, max_bytes=2_000_000):
    path = safe_path(path, must_exist=True, directory=False)
    if path.stat().st_size > max_bytes:
        raise StorageError('JSON 文件超过大小限制。')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StorageError('JSON 包含重复字段。')
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise StorageError('JSON 文件损坏。') from exc


def atomic_json(path, value):
    path = safe_path(path, directory=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = safe_path(path.with_name(f'.{path.name}.{uuid4()}.tmp'), directory=False)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    with temporary.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    safe_path(path, directory=False)
    os.replace(temporary, path)
    sync_directory(path.parent)


def sync_directory(path):
    """Persist atomic pointer publication on Linux; Windows keeps its existing contract."""
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
