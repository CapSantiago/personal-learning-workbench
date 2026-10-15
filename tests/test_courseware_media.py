"""Synthetic-only media extraction, source binding and cache safety boundaries."""
from pathlib import Path
import subprocess
from uuid import uuid4
import zipfile

import pytest

from plw import backups, courseware_media as media, db, storage, workspace
from plw.materials import MaterialService
from plw.services import LearningService

VIDEO = b'\x00\x00\x00\x18ftypmp42' + b'synthetic-video-body' * 3
R = media.R
P = media.P
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'


def uid():
    return str(uuid4())


def package(*, external=False, extension='.mp4', extra=None, reverse=False):
    ids = ('2', '1') if reverse else ('1', '2')
    parts = {
        'ppt/presentation.xml': (f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>' +
            ''.join(f'<p:sldId id="{x}" r:id="r{x}"/>' for x in ids) + '</p:sldIdLst></p:presentation>').encode(),
        'ppt/_rels/presentation.xml.rels': (f'<Relationships xmlns="{PKG}">' +
            ''.join(f'<Relationship Id="r{x}" Type="{R}/slide" Target="slides/slide{x}.xml"/>' for x in ('1', '2')) + '</Relationships>').encode(),
        'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="urn:drawing" xmlns:r="{R}"><a:videoFile r:link="v1"/><p:media r:embed="v2"/></p:sld>'.encode(),
        'ppt/slides/slide2.xml': f'<p:sld xmlns:p="{P}"/>'.encode(),
        f'ppt/media/video{extension}': VIDEO,
    }
    target = 'https://invalid.example/video.mp4' if external else f'../media/video{extension}'
    mode = ' TargetMode="External"' if external else ''
    parts['ppt/slides/_rels/slide1.xml.rels'] = (f'<Relationships xmlns="{PKG}">' +
        f'<Relationship Id="v1" Type="{R}/video" Target="{target}"{mode}/>' +
        ('' if external else f'<Relationship Id="v2" Type="http://schemas.microsoft.com/office/2007/relationships/media" Target="{target}"/>') + '</Relationships>').encode()
    return parts | (extra or {})


@pytest.fixture
def sample():
    root = storage.ROOTS[1] / ('media-tests-' + uid())
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    learning = LearningService(path)
    semester = learning.create_semester('媒体测试学期', request_id=uid())
    course = learning.create_course(semester['id'], '合成媒体课程', request_id=uid())
    (root / 'sources').mkdir()

    def create(parts=None, *, converter='Microsoft PowerPoint static PDF; includes hidden slides', pages=2,
               mode='managed_copy', suffix='.pptx'):
        source = root / 'sources' / (uid() + suffix)
        with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
            for key, value in (parts or package()).items():
                info = zipfile.ZipInfo('placeholder')
                info.filename = key  # Retain hostile backslashes: Windows normally normalizes them.
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, value)
        material = MaterialService(path).import_file(course['id'], source, mode, request_id=uid())
        identity = uid()
        pdf = path.parent / 'reading' / (identity + '.pdf')
        pdf.parent.mkdir(exist_ok=True)
        pdf.write_bytes(b'%PDF-1.7\nsynthetic-only\n%%EOF')
        with db.transaction(path) as connection:
            connection.execute('INSERT INTO reading_editions VALUES(?,?,?,?,?,?,?,?,?)',
                (identity, material['id'], storage.hash_file(source)[1], f'reading/{identity}.pdf',
                 storage.hash_file(pdf)[1], pdf.stat().st_size, pages, converter, '2026-10-13T00:00:00+00:00'))
            connection.executemany('INSERT INTO edition_pages VALUES(?,?)', ((identity, page) for page in range(1, pages + 1)))
        return media.CoursewareMedia(path), identity, source, material

    return root, path, create


def test_internal_video_deduplicates_relationships_and_tracks_actual_slide_order(sample):
    root, path, create = sample
    service, identity, source, _ = create(package(reverse=True))
    before = storage.hash_file(source)
    assert service.embedded(identity) == [] and service.animation(identity) is None
    rows = service.prepare_embedded(identity)
    assert len(rows) == 1 and rows[0]['page'] == 2
    assert rows[0]['path'].is_relative_to(root / 'cache' / path.parent.name)
    assert not rows[0]['path'].is_relative_to(path.parent)
    assert rows[0]['path'].read_bytes() == VIDEO
    assert rows[0]['mime'] == 'video/mp4' and rows[0]['playable'] is True
    assert storage.hash_file(source) == before
    assert service.messages(identity) == []


def test_cache_is_not_in_complete_backup(sample):
    root, path, create = sample
    service, identity, _, _ = create()
    service.prepare_embedded(identity)
    report = backups.create_backup(path)
    manifest = storage.read_json(Path(report['path']) / 'manifest.json')
    assert all('cache' not in f['relative_path'] for f in manifest['files'])


def test_external_video_is_never_fetched(sample):
    _, _, create = sample
    service, identity, _, _ = create(package(external=True))
    assert service.prepare_embedded(identity) == []
    assert '外部链接' in service.messages(identity)[0]


def test_unplayable_embedded_video_is_preserved_with_mime(sample):
    _, _, create = sample
    service, identity, _, _ = create(package(extension='.wmv'))
    row = service.prepare_embedded(identity)[0]
    assert row['playable'] is False and row['mime'] == 'video/x-ms-wmv'


def test_unknown_media_extension_is_skipped(sample):
    _, _, create = sample
    service, identity, _, _ = create(package(extension='.exe'))
    assert service.prepare_embedded(identity) == []
    assert service.messages(identity)


def test_same_video_on_multiple_pages_is_copied_once(sample):
    _, _, create = sample
    parts = package()
    parts['ppt/slides/slide2.xml'] = parts['ppt/slides/slide1.xml']
    parts['ppt/slides/_rels/slide2.xml.rels'] = parts['ppt/slides/_rels/slide1.xml.rels']
    service, identity, _, _ = create(parts)
    rows = service.prepare_embedded(identity)
    assert [r['page'] for r in rows] == [1, 2]
    assert rows[0]['path'] == rows[1]['path']


def test_relation_cannot_traverse_outside_package(sample):
    _, _, create = sample
    parts = package()
    parts['ppt/slides/_rels/slide1.xml.rels'] = parts['ppt/slides/_rels/slide1.xml.rels'].replace(
        b'../media/video.mp4', b'../../../outside.mp4')
    service, identity, _, _ = create(parts)
    with pytest.raises(media.MediaError, match='越界'):
        service.prepare_embedded(identity)


@pytest.mark.parametrize('converter,pages', [('user-exported PDF; slide mapping unverified', 2), ('native', 1)])
def test_unverified_page_mapping_is_rejected(sample, converter, pages):
    _, _, create = sample
    service, identity, _, _ = create(converter=converter, pages=pages)
    with pytest.raises(media.MediaError):
        service.prepare_embedded(identity)


def test_external_source_change_refuses_generation_but_existing_cache_is_bound_to_edition(sample):
    _, _, create = sample
    service, identity, source, _ = create(mode='external_reference')
    original = service.prepare_embedded(identity)[0]
    source.write_bytes(b'changed original')
    with pytest.raises(media.MediaError, match='已变化'):
        service.prepare_embedded(identity)
    assert service.embedded(identity)[0] == original


def test_managed_source_change_is_rejected(sample):
    _, path, create = sample
    service, identity, _, material = create()
    storage.relative_file(path.parent, material['managed_relpath']).write_bytes(b'changed')
    with pytest.raises(media.MediaError, match='已变化'):
        service.prepare_animation(identity)


def test_legacy_ppt_requires_save_as_pptx(sample):
    _, _, create = sample
    service, identity, _, _ = create(suffix='.ppt')
    with pytest.raises(media.MediaError, match='另存为 PPTX'):
        service.prepare_animation(identity)


@pytest.mark.parametrize('evil', ['../escape.bin', '/absolute.bin', 'C:/escape.bin', 'ppt\\media\\escape.bin'])
def test_package_path_traversal_rejected(sample, evil):
    _, _, create = sample
    service, identity, _, _ = create(package(extra={evil: b'bad'}))
    with pytest.raises(media.MediaError, match='不安全'):
        service.prepare_embedded(identity)


def test_duplicate_casefold_package_paths_rejected(sample):
    _, _, create = sample
    service, identity, _, _ = create(package(extra={'PPT/MEDIA/VIDEO.MP4': VIDEO}))
    with pytest.raises(media.MediaError, match='重复'):
        service.prepare_embedded(identity)


@pytest.mark.parametrize('constant,limit', [('MAX_ENTRIES', 1), ('MAX_MEMBER', 4), ('MAX_TOTAL', 4), ('MAX_XML', 4)])
def test_package_resource_limits(sample, monkeypatch, constant, limit):
    _, _, create = sample
    service, identity, _, _ = create()
    monkeypatch.setattr(media, constant, limit)
    with pytest.raises(media.MediaError):
        service.prepare_embedded(identity)


def test_xml_entities_rejected(sample):
    _, _, create = sample
    parts = package()
    parts['ppt/presentation.xml'] = b'<!DOCTYPE x [<!ENTITY x "bad">]><x>&x;</x>'
    service, identity, _, _ = create(parts)
    with pytest.raises(media.MediaError, match='实体'):
        service.prepare_embedded(identity)


def test_changed_cache_is_rejected(sample):
    _, _, create = sample
    service, identity, _, _ = create()
    row = service.prepare_embedded(identity)[0]
    row['path'].write_bytes(b'corrupted')
    with pytest.raises(media.MediaError, match='校验失败'):
        service.embedded(identity)
    assert service.prepare_embedded(identity)[0]['path'].read_bytes() == VIDEO


def test_manifest_cannot_escape_cache(sample):
    _, _, create = sample
    service, identity, _, _ = create()
    service.prepare_embedded(identity)
    manifest = service._directory(identity) / 'embedded.json'
    value = storage.read_json(manifest)
    value['items'][0]['relative_path'] = '../../plw.sqlite3'
    storage.atomic_json(manifest, value)
    with pytest.raises(media.MediaError):
        service.embedded(identity)


def test_restore_switch_rejects_old_media_service(sample):
    root, path, create = sample
    service, identity, _, _ = create()
    service.prepare_embedded(identity)
    new_path = workspace.create_dataset(root)
    workspace.set_active(root, new_path.parent.name, expected_dataset_id=path.parent.name)
    with pytest.raises(media.MediaError, match='切换'):
        service.embedded(identity)


def test_animation_uses_isolated_copy_and_preserves_source(sample, monkeypatch):
    root, _, create = sample
    service, identity, source, _ = create()
    original = storage.hash_file(source)
    def export(snapshot, target):
        assert snapshot.name == 'input.pptx' and snapshot.parent.parent == root / 'jobs'
        assert target.parent == snapshot.parent
        target.write_bytes(VIDEO)
    monkeypatch.setattr(media, '_export', export)
    row = service.prepare_animation(identity)
    assert row['page'] is None and row['playable'] and row['path'].read_bytes() == VIDEO
    assert storage.hash_file(source) == original


@pytest.mark.parametrize('relation_type,external', [('video', True), ('image', True), ('oleObject', False), ('vbaProject', False)])
def test_animation_rejects_external_assets_and_active_objects(sample, monkeypatch, relation_type, external):
    _, _, create = sample
    mode = ' TargetMode="External"' if external else ''
    extra = {'ppt/_rels/extra.xml.rels': f'<Relationships xmlns="{PKG}"><Relationship Id="x" Type="{R}/{relation_type}" Target="anything"{mode}/></Relationships>'.encode()}
    service, identity, _, _ = create(package(extra=extra))
    monkeypatch.setattr(media, '_export', lambda *_: pytest.fail('PowerPoint must not be invoked'))
    with pytest.raises(media.MediaError, match='外部资源或活动对象'):
        service.prepare_animation(identity)


def test_animation_failure_does_not_publish_cache_or_change_pdf(sample, monkeypatch):
    _, path, create = sample
    service, identity, _, _ = create()
    pdf = path.parent / 'reading' / (identity + '.pdf')
    before = storage.hash_file(pdf)
    def fail(*_):
        raise media.MediaError('synthetic export failure')
    monkeypatch.setattr(media, '_export', fail)
    with pytest.raises(media.MediaError):
        service.prepare_animation(identity)
    assert service.animation(identity) is None and storage.hash_file(pdf) == before


def test_source_change_during_export_does_not_publish(sample, monkeypatch):
    _, _, create = sample
    service, identity, source, _ = create(mode='external_reference')
    def export(_, target):
        target.write_bytes(VIDEO)
        source.write_bytes(b'changed while exporting')
    monkeypatch.setattr(media, '_export', export)
    with pytest.raises(media.MediaError, match='发生变化'):
        service.prepare_animation(identity)
    assert service.animation(identity) is None


def test_export_timeout_is_actionable(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 195)
    monkeypatch.setattr(media.subprocess, 'run', timeout)
    with pytest.raises(media.MediaError, match='超时'):
        media._export(Path('input.pptx'), Path('animation.mp4'))


def test_export_script_timeout_reports_retained_job_and_uncertain_office_cleanup(monkeypatch):
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **k:
        subprocess.CompletedProcess(a[0], 1, '', 'PLW_MEDIA_EXPORT_TIMEOUT'))
    with pytest.raises(media.MediaError, match='独立作业副本已保留.*无法确认导出窗口已释放'):
        media._export(Path('input.pptx'), Path('animation.mp4'))
