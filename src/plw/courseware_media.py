"""Rebuildable, edition-bound local PPTX video caches; never a backup payload."""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import subprocess
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET
import zipfile

from . import db, locking, storage, workspace

MAX_SOURCE = 512 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_VIDEOS = 100
EXPORT_TIMEOUT = 180
MIME = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm',
        '.mov': 'video/quicktime', '.wmv': 'video/x-ms-wmv', '.avi': 'video/x-msvideo',
        '.mpg': 'video/mpeg', '.mpeg': 'video/mpeg'}
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_SHA = re.compile(r'[0-9a-f]{64}\Z')


class MediaError(ValueError):
    pass


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise MediaError('媒体标识无效。')
    return value


def _package(source):
    try:
        archive = zipfile.ZipFile(source)
        seen, total = set(), 0
        if len(archive.infolist()) > MAX_ENTRIES:
            raise MediaError('PPTX 文件条目过多。')
        for item in archive.infolist():
            name = item.orig_filename
            parts = name.rstrip('/').split('/')
            if (not name or name != item.filename or name.startswith('/') or '\\' in name or ':' in name
                    or any(ord(c) < 32 for c in name)
                    or any(p in ('', '.', '..') for p in parts)
                    or name.casefold() in seen or item.flag_bits & 1
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise MediaError('PPTX 包含不安全、重复或加密的路径。')
            seen.add(name.casefold())
            total += item.file_size
            if (item.file_size > MAX_MEMBER or total > MAX_TOTAL
                    or item.file_size > 4 * 1024 * 1024
                    and item.file_size > max(item.compress_size, 1) * 200):
                raise MediaError('PPTX 解压大小或压缩比例超过限制。')
        return archive
    except Exception:
        if 'archive' in locals():
            archive.close()
        raise


def _xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_XML:
        raise MediaError('PPTX XML 超过大小限制。')
    data = archive.read(info)
    if b'\x00' in data or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise MediaError('PPTX XML 不允许文档类型或实体。')
    return ET.fromstring(data)


def _rels(archive, name):
    if name not in archive.namelist():
        return {}
    result = {}
    for node in _xml(archive, name):
        identity = node.get('Id')
        if not identity or identity in result:
            raise MediaError('PPTX 关系标识无效。')
        result[identity] = node.attrib
    return result


def _target(part, relation):
    target = relation.get('Target', '')
    if (relation.get('TargetMode') == 'External' or not target or target.startswith('/')
            or any(c in target for c in '\\:%?#') or any(ord(c) < 32 for c in target)):
        raise MediaError('不读取外部媒体或非规范媒体路径。')
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
    if normalized.startswith('../') or normalized == '..':
        raise MediaError('PPTX 媒体路径越界。')
    return normalized


def _slides(archive):
    presentation = _xml(archive, 'ppt/presentation.xml')
    relations = _rels(archive, 'ppt/_rels/presentation.xml.rels')
    entries = presentation.find(f'{{{P}}}sldIdLst')
    if entries is None:
        raise MediaError('PPTX 没有页面列表。')
    result = []
    for node in entries:
        relation = relations.get(node.get(f'{{{R}}}id'))
        if not relation or not relation.get('Type', '').endswith('/slide'):
            raise MediaError('PPTX 页面关系无效。')
        part = _target('ppt/presentation.xml', relation)
        if not part.startswith('ppt/slides/') or not part.endswith('.xml'):
            raise MediaError('PPTX 页面路径无效。')
        if part in result:
            raise MediaError('PPTX 页面关系重复。')
        result.append(part)
    return result


def _export(source, target):
    command = [r'C:\Program Files\PowerShell\7\pwsh.exe', '-NoProfile', '-File',
               str(storage.PROJECT_ROOT / 'scripts/export_courseware_video.ps1'),
               '-Source', str(source), '-Target', str(target), '-TimeoutSeconds', str(EXPORT_TIMEOUT)]
    timeout_message = ('动画导出超时。PDF 阅读不受影响，独立作业副本已保留。未关闭你的 PowerPoint；'
                       '无法确认导出窗口已释放，如 Office 仍忙请稍后检查，也可手动导出 MP4。')
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                timeout=EXPORT_TIMEOUT + 15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise MediaError(timeout_message) from exc
    if result.returncode and 'PLW_MEDIA_EXPORT_TIMEOUT' in result.stderr:
        raise MediaError(timeout_message)
    if result.returncode or not target.is_file():
        raise MediaError('PowerPoint 未完成动画导出。可手动导出 MP4；PDF 阅读不受影响。')
    if target.stat().st_size < 16 or target.stat().st_size > MAX_TOTAL:
        raise MediaError('导出视频大小无效或超过 1 GiB 限制。')
    with target.open('rb') as stream:
        if stream.read(12)[4:8] != b'ftyp':
            raise MediaError('PowerPoint 未生成有效的 MP4 文件。')


class CoursewareMedia:
    def __init__(self, path):
        self.path = Path(path)
        self.root = locking.workspace_for(self.path)
        if self.root is None:
            raise MediaError('媒体需要完整的 PLW 工作区。')

    def _edition(self, identity):
        _uuid(identity)
        if workspace.active_db(self.root) != self.path:
            raise MediaError('数据集已切换，请刷新页面。')
        with closing(db.connect_snapshot(self.path)) as connection:
            row = connection.execute('SELECT e.*, m.storage_mode, m.managed_relpath, m.reference_path, '
                'm.name, m.import_state, m.file_deleted_at FROM reading_editions e '
                'JOIN materials m ON m.id=e.material_id WHERE e.id=?', (identity,)).fetchone()
        if row is None:
            raise MediaError('阅读版本不存在。')
        return dict(row)

    def _directory(self, identity):
        return storage.safe_path(self.root / 'cache' / self.path.parent.name / 'media' / _uuid(identity), directory=True)

    def _source(self, edition):
        if edition['import_state'] != 'ready' or edition['file_deleted_at']:
            raise MediaError('原始课件不可用，无法生成媒体。')
        source = (storage.relative_file(self.path.parent, edition['managed_relpath'], must_exist=True)
                  if edition['storage_mode'] == 'managed_copy' else
                  storage.check_source(edition['reference_path'], True, db_path=self.path))
        if source.suffix.lower() != '.pptx':
            raise MediaError('此功能需要 PPTX 原文件；旧 PPT 请先在 PowerPoint 中另存为 PPTX，PDF 继续用于静态阅读。')
        if source.stat().st_size > MAX_SOURCE:
            raise MediaError('PPTX 原文件超过 512 MiB 限制。')
        if storage.hash_file(source)[1] != edition['source_sha256']:
            raise MediaError('原始课件已变化，不能与当前阅读版本的页面混用。请先生成新的阅读版本。')
        return source

    def _load(self, identity, kind):
        edition = self._edition(identity)
        directory = self._directory(identity)
        manifest = directory / (kind + '.json')
        if not manifest.exists():
            return {'items': [], 'messages': []}
        value = storage.read_json(manifest)
        if (not isinstance(value, dict) or value.get('format_version') != 1
                or value.get('edition_id') != identity or value.get('source_sha256') != edition['source_sha256']
                or not isinstance(value.get('items'), list) or len(value['items']) > MAX_VIDEOS
                or not isinstance(value.get('messages'), list)
                or any(not isinstance(m, str) or len(m) > 500 for m in value['messages'])):
            raise MediaError('媒体缓存清单无效。')
        items = []
        for row in value['items']:
            if (not isinstance(row, dict) or set(row) != {'page', 'label', 'relative_path', 'sha256', 'size_bytes', 'mime', 'playable'}
                    or type(row['size_bytes']) is not int or not 0 < row['size_bytes'] <= MAX_TOTAL
                    or not isinstance(row['sha256'], str) or not _SHA.fullmatch(row['sha256'])
                    or not isinstance(row['label'], str) or len(row['label']) > 200
                    or type(row['playable']) is not bool or not isinstance(row['relative_path'], str)):
                raise MediaError('媒体缓存记录无效。')
            if (kind == 'animation' and row['page'] is not None or kind == 'embedded'
                    and (type(row['page']) is not int or not 1 <= row['page'] <= edition['page_count'])):
                raise MediaError('媒体缓存页码无效。')
            rel = PurePosixPath(row['relative_path'])
            if (len(rel.parts) != 2 or not rel.parts[0].startswith(kind + '-')
                    or MIME.get(rel.suffix.lower()) != row['mime']
                    or row['playable'] != (rel.suffix.lower() in ('.mp4', '.m4v', '.webm'))):
                raise MediaError('媒体缓存路径或格式无效。')
            _uuid(rel.parts[0][len(kind) + 1:])
            _uuid(rel.stem)
            file = storage.relative_file(directory, row['relative_path'], must_exist=True)
            if storage.hash_file(file) != (row['size_bytes'], row['sha256']):
                raise MediaError('媒体缓存校验失败，请重新生成。')
            items.append({**{k: v for k, v in row.items() if k != 'relative_path'}, 'path': file})
        return {'items': items, 'messages': value['messages']}

    def embedded(self, edition_id):
        return self._load(edition_id, 'embedded')['items']

    def animation(self, edition_id):
        rows = self._load(edition_id, 'animation')['items']
        if len(rows) > 1:
            raise MediaError('动画缓存清单无效。')
        return rows[0] if rows else None

    def messages(self, edition_id):
        return self._load(edition_id, 'embedded')['messages']

    def _stage(self, source, edition):
        directory = storage.safe_path(self.root / 'jobs' / str(uuid4()), directory=True)
        directory.mkdir(parents=True, exist_ok=False)
        snapshot = directory / 'input.pptx'
        storage.copy_verified(source, snapshot, expected_sha256=edition['source_sha256'])
        return directory, snapshot

    def _publish(self, edition, kind, rows, messages):
        directory = self._directory(edition['id'])
        generation = directory / (kind + '-' + str(uuid4()))
        generation.mkdir(parents=True, exist_ok=False)
        manifest, published = [], {}
        for row in rows:
            file = row['path']
            if file not in published:
                target = generation / (str(uuid4()) + file.suffix.lower())
                size, digest = storage.copy_verified(file, target)
                published[file] = target, size, digest
            target, size, digest = published[file]
            manifest.append({k: v for k, v in row.items() if k != 'path'} | {
                'relative_path': target.relative_to(directory).as_posix(), 'size_bytes': size, 'sha256': digest})
        storage.atomic_json(directory / (kind + '.json'), {'format_version': 1, 'edition_id': edition['id'],
            'source_sha256': edition['source_sha256'], 'items': manifest, 'messages': messages})

    def prepare_embedded(self, edition_id):
        with locking.write_barrier(self.path):
            edition = self._edition(edition_id)
            source = self._source(edition)
            if 'mapping unverified' in edition['converter']:
                raise MediaError('手动导出的 PDF 与 PPT 页码对应尚未验证，不能自动按页放置视频。请从 PPTX 重新生成阅读版本。')
            stage, snapshot = self._stage(source, edition)
            rows, messages, copied, total = [], [], {}, 0
            try:
                with _package(snapshot) as archive:
                    slides = _slides(archive)
                    if len(slides) != edition['page_count']:
                        raise MediaError('PPTX 页数与阅读版本不一致，未生成错位的视频。')
                    for page, part in enumerate(slides, 1):
                        relations = _rels(archive, posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels'))
                        slide = _xml(archive, part)
                        ids = {node.get(f'{{{R}}}link') for node in slide.iter() if node.tag.endswith('}videoFile')}
                        # Some producers only emit the p14:media embedding relationship.
                        ids.update(node.get(f'{{{R}}}embed') for node in slide.iter() if node.tag.endswith('}media'))
                        selected = set()
                        for identity in sorted(ids - {None}):
                            relation = relations.get(identity)
                            if not relation or not relation.get('Type', '').endswith(('/video', '/media')):
                                continue
                            if relation.get('TargetMode') == 'External':
                                messages.append(f'第 {page} 页的外部链接媒体未读取；请在 PowerPoint 中将视频嵌入文件。')
                                continue
                            target = _target(part, relation)
                            extension = PurePosixPath(target).suffix.lower()
                            if not target.startswith('ppt/media/') or extension not in MIME:
                                messages.append(f'第 {page} 页包含尚不支持的视频格式，已跳过。')
                                continue
                            if target in selected:
                                continue
                            selected.add(target)
                            if len(rows) >= MAX_VIDEOS:
                                raise MediaError('课件内视频数量超过 100 个。')
                            info = archive.getinfo(target)
                            if not info.file_size:
                                raise MediaError('PPTX 中的视频为空。')
                            if target not in copied:
                                total += info.file_size
                                if total > MAX_TOTAL:
                                    raise MediaError('内嵌视频总量超过 1 GiB。')
                                output = stage / (str(uuid4()) + extension)
                                with archive.open(info) as reader, output.open('xb') as writer:
                                    written = 0
                                    while chunk := reader.read(1024 * 1024):
                                        written += len(chunk)
                                        if written > info.file_size or written > MAX_MEMBER:
                                            raise MediaError('视频解压大小不一致。')
                                        writer.write(chunk)
                                    writer.flush()
                                    os.fsync(writer.fileno())
                                copied[target] = output
                            rows.append({'page': page, 'label': f'第 {page} 页 · 视频 {len(selected)}',
                                'path': copied[target], 'mime': MIME[extension],
                                'playable': extension in ('.mp4', '.m4v', '.webm')})
                if storage.hash_file(source)[1] != edition['source_sha256']:
                    raise MediaError('生成期间原始课件发生变化，请重试。')
                self._publish(edition, 'embedded', rows, list(dict.fromkeys(messages)))
            except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
                raise MediaError('PPTX 文件结构损坏，未发布媒体缓存。') from exc
            return self.embedded(edition_id)

    def prepare_animation(self, edition_id):
        with locking.write_barrier(self.path):
            edition = self._edition(edition_id)
            source = self._source(edition)
            stage, snapshot = self._stage(source, edition)
            try:
                with _package(snapshot) as archive:
                    if len(_slides(archive)) > 300:
                        raise MediaError('超过 300 页，请使用 PowerPoint 手动导出动画视频。')
                    for name in archive.namelist():
                        if name.endswith('.rels'):
                            for relation in _rels(archive, name).values():
                                kind = relation.get('Type', '').rsplit('/', 1)[-1].lower()
                                if (relation.get('TargetMode') == 'External' and kind != 'hyperlink'
                                        or kind in ('oleobject', 'control', 'activexcontrol', 'vbaproject')):
                                    raise MediaError('课件包含外部资源或活动对象。为保持离线，请在 PowerPoint 中处理后手动导出 MP4。')
                output = stage / 'animation.mp4'
                _export(snapshot, output)
                if storage.hash_file(source)[1] != edition['source_sha256']:
                    raise MediaError('导出期间原始课件发生变化，请重试。')
                self._publish(edition, 'animation', [{'page': None, 'label': '课件动画回放',
                    'path': output, 'mime': MIME['.mp4'], 'playable': True}], [])
            except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
                raise MediaError('PPTX 文件结构损坏，未生成动画。') from exc
            return self.animation(edition_id)
