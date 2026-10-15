"""Reentrant Windows cross-process barriers for app writes and dataset switches."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading

from . import storage, platform_lock

_registry_guard = threading.Lock()
_registry = {}
_local = threading.local()
LOCK_TIMEOUT = 3.0


class LockError(RuntimeError):
    pass


def workspace_for(db_path):
    path = Path(db_path)
    return path.parent.parent.parent if path.parent.parent.name == 'datasets' else None


@contextmanager
def _lock(path):
    path = storage.safe_path(path, directory=False)
    key = os.path.normcase(str(path))
    with _registry_guard:
        mutex = _registry.setdefault(key, threading.RLock())
    if not mutex.acquire(timeout=LOCK_TIMEOUT):
        raise LockError('正在备份、恢复或写入，请稍后重试。')
    holds = getattr(_local, 'holds', None)
    if holds is None:
        holds = _local.holds = {}
    try:
        if key in holds:
            holds[key] += 1
            try:
                yield
            finally:
                holds[key] -= 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        storage.safe_path(path, directory=False)
        with path.open('a+b') as stream:
            if os.fstat(stream.fileno()).st_nlink != 1:
                raise LockError('锁文件有额外链接。')
            stream.seek(0, 2)
            if not stream.tell():
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            try:
                platform_lock.acquire(stream)
            except OSError as exc:
                raise LockError('另一进程正在使用数据集，请停止维护操作后重试。') from exc
            holds[key] = 1
            try:
                yield
            finally:
                holds.pop(key)
                stream.seek(0)
                platform_lock.release(stream)
    finally:
        mutex.release()


@contextmanager
def workspace_lock(workspace):
    with _lock(Path(workspace) / 'control' / '.write.lock'):
        yield


@contextmanager
def maintenance_barrier(workspace):
    key = os.path.normcase(str(Path(workspace)))
    with workspace_lock(workspace):
        maintenance = getattr(_local, 'maintenance', None)
        if maintenance is None:
            maintenance = _local.maintenance = {}
        maintenance[key] = maintenance.get(key, 0) + 1
        try:
            yield
        finally:
            maintenance[key] -= 1
            if not maintenance[key]:
                del maintenance[key]


@contextmanager
def write_barrier(db_path):
    path = Path(db_path)
    workspace = workspace_for(path)
    # Legacy M1 uses SQLite's existing writer transaction. M2 operations only
    # accept storage's synthetic roots; all workspace writers share one lock.
    if path.is_relative_to(storage.PROJECT_ROOT / '.sandbox' / 'm1'):
        yield
        return
    lock_path = workspace / 'control' / '.write.lock' if workspace else path.parent / '.write.lock'
    with _lock(lock_path):
        if workspace:
            from .workspace import active_db, WorkspaceError
            try:
                current = active_db(workspace)
            except (WorkspaceError, storage.StorageError, OSError, TypeError) as exc:
                raise LockError('活动数据集指针无效，已停止写入；请检查恢复状态。') from exc
            if current != path:
                raise LockError('数据集已切换；旧页面不能继续写入，请刷新。')
            journal_path = workspace / 'control' / 'restore-journal.json'
            if journal_path.exists() and not getattr(_local, 'maintenance', {}).get(os.path.normcase(str(workspace))):
                try:
                    journal = storage.read_json(journal_path)
                    phase = journal.get('phase')
                    expected = journal.get('new_dataset_id') if phase == 'complete' else journal.get('old_dataset_id')
                    if journal.get('journal_version') != 1 or phase not in ('complete', 'rolled_back', 'failed') or expected != path.parent.name:
                        raise ValueError('Unresolved restore')
                except (storage.StorageError, OSError, ValueError, AttributeError, TypeError) as exc:
                    raise LockError('存在尚未核对的恢复过程，请到数据与备份页面先核对或回滚。') from exc
        yield


@contextmanager
def initialization_barrier(db_path):
    path = Path(db_path)
    workspace = workspace_for(path)
    if not workspace:
        yield
        return
    with workspace_lock(workspace):
        if path.exists() and path.stat().st_size:
            with write_barrier(path):
                yield
        else:
            # Only explicit maintenance creates a new dataset file; it has no
            # application writer until set_active publishes its identity.
            yield
