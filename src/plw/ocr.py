"""Offline OCR whose disposable cache stays outside authoritative datasets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4, UUID

from . import db, locking, storage, workspace
from .reader_runtime import PYTHON

MAX_BATCH_PAGES = 20
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
CACHE_VERSION = 1
PROJECT = Path(__file__).resolve().parents[2]
WINDOWS = Path(os.environ.get('SystemRoot', r'C:\Windows'))


class OcrError(ValueError):
    pass


def _run(command, timeout):
    try:
        result = subprocess.run([str(value) for value in command], capture_output=True,
                                text=True, encoding='utf-8-sig', errors='replace',
                                timeout=timeout,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OcrError('本地 OCR 未完成或超时，请稍后重试。') from error
    if result.returncode:
        raise OcrError('本地 OCR 未完成：' + (result.stderr or result.stdout).strip()[-500:])
    return result.stdout


class OcrService:
    def __init__(self, path):
        self.path = storage.safe_path(Path(path), must_exist=True, directory=False)
        self.workspace = locking.workspace_for(self.path)
        if self.workspace is None:
            raise OcrError('OCR 需要已初始化的 PLW 学习库。')
        self.cache = storage.safe_path(self.workspace / 'cache' / self.path.parent.name / 'ocr', directory=True)

    def _active(self):
        if workspace.active_db(self.workspace) != self.path:
            raise OcrError('学习库已切换，请刷新后重新识别。')

    def _edition(self, edition_id):
        self._active()
        try:
            valid = isinstance(edition_id, str) and str(UUID(edition_id)) == edition_id
        except ValueError:
            valid = False
        if not valid:
            raise OcrError('阅读版本 ID 无效。')
        with db.transaction(self.path, write=False) as connection:
            row = connection.execute('SELECT * FROM reading_editions WHERE id=?', (edition_id,)).fetchone()
        if row is None:
            raise OcrError('阅读版本不存在。')
        edition = dict(row)
        source = storage.relative_file(self.path.parent, edition['pdf_relpath'], must_exist=True)
        if storage.hash_file(source) != (edition['size_bytes'], edition['pdf_sha256']):
            raise OcrError('阅读 PDF 校验失败，已停止识别。请检查或恢复该阅读版本。')
        return edition, source

    def _page_cache(self, edition, page):
        return storage.safe_path(self.cache / edition['id'] / edition['pdf_sha256'] / (str(page) + '.json'), directory=False)

    def _cached(self, file, expected):
        if not file.exists():
            return None
        payload = storage.read_json(file, max_bytes=800_000)
        if (not isinstance(payload, dict) or any(payload.get(key) != value for key, value in expected.items())
                or not isinstance(payload.get('text'), str) or len(payload['text']) > MAX_TEXT_CHARS
                or payload.get('text_sha256') != hashlib.sha256(payload['text'].encode('utf-8')).hexdigest()):
            raise OcrError('OCR 缓存校验失败，请重新识别对应页或图片。')
        return payload['text']

    def texts(self, edition_id):
        edition, _ = self._edition(edition_id)
        result = {}
        total = 0
        directory = self._page_cache(edition, 1).parent
        if not directory.exists():
            return result
        storage.safe_path(directory, must_exist=True, directory=True)
        for file in directory.iterdir():
            if not file.name.endswith('.json') or not file.stem.isdecimal():
                continue
            page = int(file.stem)
            if not 1 <= page <= edition['page_count'] or file.stem != str(page):
                continue
            text = self._cached(storage.safe_path(file, directory=False),
                                {'version': CACHE_VERSION, 'source_sha256': edition['pdf_sha256'], 'page': page})
            if text is not None:
                total += len(text)
                if total > 4_000_000:
                    raise OcrError('此课件 OCR 文本超过显示限制，请分卷阅读。')
                result[str(page)] = text
        self._active()
        return result

    def _job(self):
        with locking.write_barrier(self.path):
            self._active()
            job = storage.safe_path(self.cache / 'jobs' / str(uuid4()), directory=True)
            job.mkdir(parents=True)
            storage.safe_path(job, must_exist=True, directory=True)
        return job

    def _cleanup_job(self, job):
        # Only our fixed temporary filenames in this newly generated job can
        # be removed. Never traverse a link or remove unknown/user files.
        try:
            storage.safe_path(job, root=self.cache / 'jobs', must_exist=True, directory=True)
            for name in ('OcrHelper.exe', 'rendered.png', 'input.png', 'input.jpg', 'input.jpeg'):
                file = storage.safe_path(job / name, root=job, directory=False)
                if file.exists():
                    file.unlink()
            job.rmdir()
        except (OSError, storage.StorageError):
            pass

    def _helper(self, job):
        compiler = WINDOWS / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        runtime = WINDOWS / 'Microsoft.NET/Framework64/v4.0.30319'
        references = [WINDOWS / ('System32/WinMetadata/Windows.' + name + '.winmd')
                      for name in ('Media', 'Globalization', 'Foundation', 'Storage', 'Graphics')]
        references += [runtime / 'System.Web.Extensions.dll',
                       WINDOWS / 'Microsoft.NET/assembly/GAC_MSIL/System.Runtime/v4.0_4.0.0.0__b03f5f7f11d50a3a/System.Runtime.dll',
                       WINDOWS / 'Microsoft.NET/assembly/GAC_MSIL/System.Runtime.InteropServices.WindowsRuntime/v4.0_4.0.0.0__b03f5f7f11d50a3a/System.Runtime.InteropServices.WindowsRuntime.dll']
        if os.name != 'nt' or not all(file.is_file() for file in [compiler, PYTHON, *references]):
            raise OcrError('此电脑缺少本地 Windows OCR 运行条件；当前环境未安装或更改任何组件。')
        helper = storage.safe_path(job / 'OcrHelper.exe', directory=False)
        _run([compiler, '/nologo', '/target:exe', '/out:' + str(helper),
              *['/reference:' + str(file) for file in references], PROJECT / 'scripts/ocr_helper.cs'], 30)
        storage.safe_path(helper, must_exist=True, directory=False)
        return helper

    def capabilities(self):
        job = None
        try:
            self._active()
            job = self._job()
            helper = self._helper(job)
            result = json.loads(_run([helper, '--capabilities'], 15))
            languages = result.get('languages', [])
            available = any(tag.startswith(('zh-Hans', 'en')) for tag in languages)
            return {**result, 'available': available, 'reason': '' if available else '此电脑未提供中文或英文 OCR 语言。'}
        except (OcrError, OSError, ValueError, locking.LockError, storage.StorageError) as error:
            return {'available': False, 'languages': [], 'max_image_dimension': 0, 'reason': str(error)}
        finally:
            if job is not None:
                self._cleanup_job(job)

    def _recognize(self, source, job, helper, *, page=None):
        command = [PYTHON, '-B', '-X', 'utf8', PROJECT / 'scripts/ocr_worker.py',
                   'image' if page is None else 'pdf', source, job, helper]
        if page is not None:
            command += ['--page', str(page)]
        result = json.loads(_run(command, 60))
        if not isinstance(result.get('text'), str) or len(result['text']) > MAX_TEXT_CHARS:
            raise OcrError('OCR 返回内容无效。')
        return result

    def _save(self, target, metadata, result):
        text = result['text']
        with locking.write_barrier(self.path):
            self._active()
            storage.atomic_json(target, {**metadata, 'version': CACHE_VERSION, 'text': text,
                                         'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                                         'engine': result.get('engine'), 'language': result.get('language')})

    def recognize_pages(self, edition_id, pages, progress=None):
        edition, source = self._edition(edition_id)
        pages = list(pages)
        if not pages or len(pages) > MAX_BATCH_PAGES:
            raise OcrError('每批请选择 1–20 页进行识别。')
        if any(type(page) is not int or not 1 <= page <= edition['page_count'] for page in pages):
            raise OcrError('识别页码超出范围。')
        pages = list(dict.fromkeys(pages))
        for index, page in enumerate(pages, 1):
            self._active()
            job = self._job()
            try:
                helper = self._helper(job)
                result = self._recognize(source, job, helper, page=page)
                self._edition(edition_id)  # Recheck the original bytes after each operation.
                self._save(self._page_cache(edition, page), {'source_sha256': edition['pdf_sha256'], 'page': page}, result)
            finally:
                self._cleanup_job(job)
            if progress is not None:
                progress(index, len(pages), page)
        return self.texts(edition_id)

    def recognize_image(self, filename, content):
        self._active()
        if (not isinstance(filename, str) or Path(filename).name != filename
                or Path(filename).suffix.lower() not in ('.png', '.jpg', '.jpeg')):
            raise OcrError('请选择 PNG 或 JPG 图片。')
        if not isinstance(content, bytes) or not 0 < len(content) <= MAX_IMAGE_BYTES:
            raise OcrError('图片不能为空，且每张最多 20 MB。')
        digest = hashlib.sha256(content).hexdigest()
        target = storage.safe_path(self.cache / 'images' / (digest + '.json'), directory=False)
        job = self._job()
        try:
            source = storage.safe_path(job / ('input' + Path(filename).suffix.lower()), directory=False)
            with source.open('xb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            helper = self._helper(job)
            if storage.hash_file(source) != (len(content), digest):
                raise OcrError('识别期间图片内容发生变化，请重新选择图片。')
            result = self._recognize(source, job, helper)
            self._active()
            if storage.hash_file(source) != (len(content), digest):
                raise OcrError('识别期间图片内容发生变化，请重新选择图片。')
            self._save(target, {'source_sha256': digest}, result)
            return result['text']
        finally:
            self._cleanup_job(job)
