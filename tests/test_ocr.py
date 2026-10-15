"""Offline OCR boundaries and real engine smoke tests, using generated files only."""
from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageDraw, ImageFont

from plw import backups, db, storage, workspace
from plw.materials import MaterialService
from plw.ocr import OcrService, OcrError, MAX_IMAGE_BYTES
from plw.services import LearningService
from plw.workbench import Workbench


def uid():
    return str(uuid4())


@pytest.fixture
def sample():
    root = storage.ROOTS[1] / ('ocr-' + uid())
    workspace.initialize_workspace(root)
    path = workspace.active_db(root)
    learning = LearningService(path)
    semester = learning.create_semester('OCR 合成学期', request_id=uid())
    course = learning.create_course(semester['id'], 'OCR 合成课程', request_id=uid())
    image = Image.new('RGB', (1400, 700), 'white')
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 56)
    drawing = ImageDraw.Draw(image)
    drawing.text((70, 100), '机器人学习工作台', fill='black', font=font)
    drawing.text((70, 240), 'OCR TEST 2026', fill='black', font=font)
    source = root / 'sources/合成 扫描页.pdf'
    source.parent.mkdir()
    image.save(source, 'PDF', resolution=144, save_all=True, append_images=[image])
    material = MaterialService(path).import_file(course['id'], source, 'managed_copy', request_id=uid())
    edition = Workbench(path).create_edition(material['id'], uid(), local_copy_confirmed=True)
    return root, path, OcrService(path), edition, image


def mock_engine(monkeypatch, service, text='识别结果'):
    monkeypatch.setattr(service, '_helper', lambda job: job / 'unused.exe')
    monkeypatch.setattr(service, '_recognize', lambda *args, **kwargs:
                        {'text': text, 'engine': 'synthetic', 'language': 'zh-Hans-CN'})


def normalized(text):
    return ''.join(text.split()).casefold()


def test_real_offline_pdf_ocr_and_backup_excludes_rebuildable_cache(sample):
    root, path, service, edition, _ = sample
    capabilities = service.capabilities()
    if not capabilities['available']:
        pytest.skip(capabilities['reason'])
    with db.transaction(path, write=False) as connection:
        row = dict(connection.execute('SELECT * FROM reading_editions WHERE id=?', (edition,)).fetchone())
    pdf = path.parent / row['pdf_relpath']
    original = storage.hash_file(pdf)
    progress = []
    result = service.recognize_pages(edition, [2, 1], lambda *args: progress.append(args))
    assert set(result) == {'1', '2'}
    assert all('ocrtest2026' in normalized(text) for text in result.values())
    if any(tag.startswith('zh-Hans') for tag in capabilities['languages']):
        assert all('机器人学习工作台' in normalized(text) for text in result.values())
    assert progress == [(1, 2, 2), (2, 2, 1)]
    assert service.texts(edition) == result
    assert storage.hash_file(pdf) == original
    assert service.cache.is_relative_to(root / 'cache' / path.parent.name)
    assert not list((service.cache / 'jobs').iterdir())
    assert not (path.parent / 'ocr').exists()
    report = backups.create_backup(path)
    assert report['complete']


@pytest.mark.parametrize('format,suffix', [('PNG', 'png'), ('JPEG', 'jpg')])
def test_real_offline_image_ocr(sample, format, suffix):
    _, _, service, _, image = sample
    capabilities = service.capabilities()
    if not capabilities['available']:
        pytest.skip(capabilities['reason'])
    stream = BytesIO()
    image.save(stream, format=format)
    content = stream.getvalue()
    assert 'ocrtest2026' in normalized(service.recognize_image('中文 图片.' + suffix, content))
    assert stream.getvalue() == content
    assert not list((service.cache / 'jobs').iterdir())


@pytest.mark.parametrize('pages', [[], list(range(1, 22)), [0], [3], [True], [1.5], ['1']])
def test_page_bounds_precede_recognition(sample, monkeypatch, pages):
    _, _, service, edition, _ = sample
    monkeypatch.setattr(service, '_helper', lambda job: pytest.fail('Must reject before OCR'))
    with pytest.raises(OcrError):
        service.recognize_pages(edition, pages)
    assert service.texts(edition) == {}


def test_pdf_hash_mismatch_does_not_run_ocr(sample, monkeypatch):
    _, path, service, edition, _ = sample
    mock_engine(monkeypatch, service)
    with db.transaction(path, write=False) as connection:
        rel = connection.execute('SELECT pdf_relpath FROM reading_editions WHERE id=?', (edition,)).fetchone()[0]
    (path.parent / rel).write_bytes(b'corrupt synthetic PDF')
    with pytest.raises(OcrError, match='校验失败'):
        service.recognize_pages(edition, [1])


def test_cache_isolated_by_edition_and_rejects_tampered_text(sample, monkeypatch):
    _, path, service, edition, _ = sample
    mock_engine(monkeypatch, service)
    assert service.recognize_pages(edition, [1, 1]) == {'1': '识别结果'}
    with db.transaction(path, write=False) as connection:
        material = connection.execute('SELECT material_id FROM reading_editions WHERE id=?', (edition,)).fetchone()[0]
    another = Workbench(path).create_edition(material, uid(), local_copy_confirmed=True)
    assert service.texts(another) == {}
    row, _ = service._edition(edition)
    cache = service._page_cache(row, 1)
    payload = json.loads(cache.read_text(encoding='utf-8'))
    payload['text'] = 'altered cache'
    cache.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(OcrError, match='缓存校验失败'):
        service.texts(edition)
    assert service.recognize_pages(edition, [1]) == {'1': '识别结果'}


def test_ocr_failure_keeps_completed_pages_and_original_pdf(sample, monkeypatch):
    _, _, service, edition, _ = sample
    mock_engine(monkeypatch, service)
    _, source = service._edition(edition)
    before = storage.hash_file(source)
    def recognize(*args, page):
        if page == 2:
            raise OcrError('synthetic failure')
        return {'text': 'page one', 'engine': 'synthetic'}
    monkeypatch.setattr(service, '_recognize', recognize)
    with pytest.raises(OcrError):
        service.recognize_pages(edition, [1, 2])
    assert service.texts(edition) == {'1': 'page one'}
    assert storage.hash_file(source) == before


@pytest.mark.parametrize('filename,content', [('../escape.png', b'fake'), ('x.pdf', b'fake'),
                                              ('image.png', b''), ('image.png', b'x' * (MAX_IMAGE_BYTES + 1))],
                         ids=['path', 'format', 'empty', 'size'])
def test_image_upload_boundaries(sample, monkeypatch, filename, content):
    _, _, service, _, _ = sample
    monkeypatch.setattr(service, '_helper', lambda job: pytest.fail('Must reject before OCR'))
    with pytest.raises(OcrError):
        service.recognize_image(filename, content)


def test_invalid_image_contents_are_rejected(sample):
    _, _, service, _, _ = sample
    capabilities = service.capabilities()
    if not capabilities['available']:
        pytest.skip(capabilities['reason'])
    with pytest.raises(OcrError):
        service.recognize_image('broken.png', b'not a PNG')
    assert not list((service.cache / 'jobs').iterdir())


def test_oversized_image_pixels_rejected_before_decoding(sample):
    _, _, service, _, _ = sample
    stream = BytesIO()
    Image.new('RGB', (5000, 4000), 'white').save(stream, format='PNG')
    with pytest.raises(OcrError, match='1600 万像素'):
        service.recognize_image('oversized.png', stream.getvalue())


def test_pdf_changed_during_ocr_is_not_cached(sample, monkeypatch):
    _, _, service, edition, _ = sample
    monkeypatch.setattr(service, '_helper', lambda job: job / 'unused.exe')
    def changed(source, *args, **kwargs):
        source.write_bytes(source.read_bytes() + b'\n%changed while recognizing\n')
        return {'text': 'must not publish', 'engine': 'synthetic'}
    monkeypatch.setattr(service, '_recognize', changed)
    with pytest.raises(OcrError, match='校验失败'):
        service.recognize_pages(edition, [1])
    assert not list(service.cache.rglob('*.json'))


def test_dataset_switch_during_ocr_does_not_publish_cache(sample, monkeypatch):
    _, path, service, edition, _ = sample
    monkeypatch.setattr(service, '_helper', lambda job: job / 'unused.exe')
    def switched(*args, **kwargs):
        monkeypatch.setattr(workspace, 'active_db', lambda root: path.parent.parent / uid() / 'plw.sqlite3')
        return {'text': 'must not publish', 'engine': 'synthetic'}
    monkeypatch.setattr(service, '_recognize', switched)
    with pytest.raises(OcrError, match='学习库已切换'):
        service.recognize_pages(edition, [1])
    assert not list(service.cache.rglob('*.json'))


def test_missing_engine_reports_clear_capability_failure(sample, monkeypatch):
    _, _, service, _, _ = sample
    def unavailable(job):
        raise OcrError('此电脑缺少本地 Windows OCR 运行条件')
    monkeypatch.setattr(service, '_helper', unavailable)
    assert service.capabilities() == {'available': False, 'languages': [], 'max_image_dimension': 0,
                                      'reason': '此电脑缺少本地 Windows OCR 运行条件'}


def test_dataset_switch_blocks_old_ocr_cache_reads_and_writes(sample, monkeypatch):
    _, path, service, edition, image = sample
    mock_engine(monkeypatch, service)
    monkeypatch.setattr(workspace, 'active_db', lambda root: path.parent.parent / uid() / 'plw.sqlite3')
    with pytest.raises(OcrError, match='学习库已切换'):
        service.texts(edition)
    with pytest.raises(OcrError, match='学习库已切换'):
        service.recognize_pages(edition, [1])
    with pytest.raises(OcrError, match='学习库已切换'):
        service.recognize_image('image.png', b'fake')
