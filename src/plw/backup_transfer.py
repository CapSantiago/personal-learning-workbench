"""Transport the existing verified directory backup as a ZIP, without changing format."""
from pathlib import Path
import hashlib
import stat
import time
from uuid import uuid4
import zipfile
import threading

from . import backups, storage, workspace

MAX_BYTES = 20 * 1024**3
_downloads = {}
_guard = threading.Lock()


def pack_backup(directory, output=None):
    directory = storage.safe_path(directory, must_exist=True, directory=True)
    report = backups.verify_backup(directory)
    output = storage.safe_path(output or directory.parent / ('PLW-' + report['id'] + '.zip'), directory=False)
    if output.is_relative_to(directory):
        raise ValueError('备份包必须保存在备份目录之外。')
    files = sorted(p for p in directory.rglob('*') if p.is_file())
    expected = {p.relative_to(directory).as_posix(): storage.hash_file(p) for p in files}
    total = sum(p.stat().st_size for p in files)
    if total > MAX_BYTES:
        raise ValueError('备份超过20 GiB，请使用服务器文件传输并保留完整清单。')
    output.parent.mkdir(parents=True, exist_ok=True)
    backups._space(output.parent, total + 1024 * 1024)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for file in files:
            storage.safe_path(file, root=directory, must_exist=True, directory=False)
            archive.write(file, file.relative_to(directory).as_posix())
    # A concurrent edit to the input cannot silently publish a corrupted archive.
    with zipfile.ZipFile(output) as archive:
        for entry in archive.infolist():
            digest = hashlib.sha256()
            size = 0
            with archive.open(entry) as source:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            if (size, digest.hexdigest()) != expected[entry.filename]:
                raise ValueError('备份包校验失败，保留文件供检查。')
    if backups.verify_backup(directory)['manifest_sha256'] != report['manifest_sha256']:
        raise ValueError('打包期间备份清单发生变化。')
    size, digest = storage.hash_file(output)
    return dict(report, archive_path=str(output), archive_size=size, archive_sha256=digest)


def unpack_backup(filename, destination_parent):
    """Extract into a new isolated directory, then verify before any restore is allowed."""
    filename = storage.safe_path(filename, must_exist=True, directory=False, source_only=True)
    if filename.stat().st_size > MAX_BYTES:
        raise ValueError('备份包超过20 GiB。')
    parent = storage.safe_path(destination_parent, directory=True)
    with zipfile.ZipFile(filename) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= backups.MAX_FILES + 4:
            raise ValueError('备份包文件数无效。')
        names = set()
        for item in entries:
            name = backups._relative(item.filename)
            if (item.is_dir() or name.casefold() in names or item.flag_bits & 1
                    or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG)
                    or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or any(p.endswith((' ', '.')) or p.split('.')[0].upper() in storage.RESERVED
                           or any(c in p for c in '<>:"|?*') or any(ord(c)<32 for c in p)
                           for p in name.split('/'))):
                raise ValueError('备份包包含链接、重复或不安全路径。')
            names.add(name.casefold())
        total = sum(item.file_size for item in entries)
        if total > MAX_BYTES:
            raise ValueError('解压容量超过20 GiB。')
        parent.mkdir(parents=True, exist_ok=True)
        backups._space(parent, total + 1024 * 1024)
        target = parent / ('import-' + str(uuid4()))
        target.mkdir()
        for item in entries:
            output = storage.relative_file(target, item.filename)
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, output.open('xb') as dest:
                remaining = item.file_size
                while chunk := source.read(min(1024 * 1024, remaining + 1)):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise ValueError('备份包实际容量与清单不符。')
                    dest.write(chunk)
                if remaining:
                    raise ValueError('备份包文件不完整。')
        return backups.verify_backup(target)


def register_download(report):
    path = storage.safe_path(report['archive_path'], must_exist=True, directory=False)
    if storage.hash_file(path) != (report['archive_size'], report['archive_sha256']):
        raise ValueError('备份包发生变化，请重新生成。')
    with _guard:
        now = time.monotonic()
        for key in list(_downloads):
            if _downloads[key]['expires'] < now:
                del _downloads[key]
        key = uuid4().hex + uuid4().hex
        _downloads[key] = dict(report, expires=now + 43200)
    return '/plw-backup-download/' + key


def routes():
    from starlette.responses import FileResponse, JSONResponse, Response
    from starlette.routing import Route

    def download(request):
        with _guard:
            record = _downloads.get(request.path_params['key'])
        if not record or record['expires'] < time.monotonic():
            return Response(status_code=404)
        try:
            path = storage.safe_path(record['archive_path'], must_exist=True, directory=False)
            if storage.hash_file(path) != (record['archive_size'], record['archive_sha256']):
                return Response(status_code=409)
        except (ValueError, OSError, storage.StorageError):
            return Response(status_code=404)
        return FileResponse(path, media_type='application/zip', filename=path.name,
                            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    return [Route('/plw-backup-download/{key}', download, methods=['GET'])]
