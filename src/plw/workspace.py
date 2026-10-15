"""Explicit synthetic dataset creation and compare-and-swap active pointer."""
from datetime import datetime, UTC
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from . import db, storage, locking


class WorkspaceError(RuntimeError):
    pass


def _root(root):
    root = storage.safe_path(root, directory=True)
    if root == storage.ROOTS[1]:
        raise WorkspaceError('测试工作区必须使用独立子目录。')
    return root


def dataset_db(root, dataset_id):
    root = _root(root)
    try:
        if str(UUID(dataset_id)) != dataset_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise WorkspaceError('数据集 ID 必须是规范 UUID。') from exc
    return storage.safe_path(root / 'datasets' / dataset_id / 'plw.sqlite3', directory=False)


def active_db(root):
    root = _root(root)
    value = storage.read_json(root / 'control' / 'active.json')
    if not isinstance(value, dict) or value.get('format_version') != 1:
        raise WorkspaceError('活动指针格式不受支持。')
    path = dataset_db(root, value.get('dataset_id'))
    storage.safe_path(path, must_exist=True, directory=False)
    identity = storage.read_json(path.parent / 'config.json')
    if identity != {'format_version': 1, 'dataset_id': path.parent.name}:
        raise WorkspaceError('活动数据集身份不匹配。')
    return path


def describe(root):
    path = active_db(root)
    return {'workspace': str(Path(root)), 'dataset_id': path.parent.name, 'db_path': str(path)}


def create_dataset(root):
    root = _root(root)
    with locking.workspace_lock(root):
        identity = str(uuid4())
        path = dataset_db(root, identity)
        path.parent.mkdir(parents=True, exist_ok=False)
        db.initialize(path)
        storage.atomic_json(path.parent / 'config.json', {'format_version': 1, 'dataset_id': identity})
        return path


def set_active(root, dataset_id, *, expected_dataset_id):
    root = _root(root)
    with locking.workspace_lock(root):
        target = dataset_db(root, dataset_id)
        storage.safe_path(target, must_exist=True, directory=False)
        identity = storage.read_json(target.parent / 'config.json')
        if identity != {'format_version': 1, 'dataset_id': dataset_id}:
            raise WorkspaceError('新数据集身份无效。')
        with closing(db.connect_snapshot(target)) as connection:
            if connection.execute('PRAGMA integrity_check').fetchall()[0][0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
                raise WorkspaceError('新数据集未通过数据库验证。')
        pointer = root / 'control' / 'active.json'
        previous = storage.read_json(pointer).get('dataset_id') if pointer.exists() else None
        if previous != expected_dataset_id:
            raise WorkspaceError('活动数据集已经变化，请重新预览恢复范围。')
        storage.atomic_json(pointer, {'format_version': 1, 'dataset_id': dataset_id, 'updated_at': datetime.now(UTC).isoformat()})
        return describe(root)


def initialize_workspace(root):
    root = _root(root)
    with locking.workspace_lock(root):
        if (root / 'control' / 'active.json').exists():
            return describe(root)
        if (root / 'datasets').exists() and any((root / 'datasets').iterdir()):
            raise WorkspaceError('已有无活动指针的数据集，先检查中断状态；不会自动初始化另一套数据。')
        path = create_dataset(root)
        return set_active(root, path.parent.name, expected_dataset_id=None)
