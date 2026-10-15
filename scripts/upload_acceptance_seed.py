"""Create a new synthetic workspace for browser upload acceptance; no real data."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from plw import storage, workspace
from plw.services import LearningService


def main():
    root = storage.ROOTS[1] / ('upload-' + str(uuid4()))
    workspace.initialize_workspace(root)
    database = workspace.active_db(root)
    service = LearningService(database)
    semester = service.create_semester('多文件导入 · 合成验收', request_id=str(uuid4()))
    courses = [service.create_course(semester['id'], name, request_id=str(uuid4()))
               for name in ('自动控制原理 · 上传验收', '机器人学 · 上传验收')]
    sources = root / 'sources'
    sources.mkdir()
    fixtures = storage.PROJECT_ROOT / '.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'
    files = {}
    for key, name in (
        ('native', '原生 PDF 中文课件.pdf'),
        ('rotated', '旋转 裁剪.pdf'),
        ('scanned', '图片型 PDF.pdf'),
        ('presentation', '宽屏 合成课件.pptx'),
    ):
        target = sources / name
        shutil.copyfile(fixtures / name, target)
        files[key] = target
    damaged = sources / '合成损坏课件.pdf'
    damaged.write_bytes(b'%PDF-1.7\nSynthetic invalid PDF without a trailer.\n')
    files['damaged'] = damaged
    changed = sources / '同名不同内容'
    changed.mkdir()
    files['changed_name'] = changed / files['native'].name
    shutil.copyfile(files['scanned'], files['changed_name'])
    evidence = root / 'evidence'
    evidence.mkdir()
    setup = {
        'root': str(root), 'database': str(database),
        'courses': [{'id': c['id'], 'name': c['name']} for c in courses],
        'files': {key: {'path': str(value), 'name': value.name,
                        'sha256': hashlib.sha256(value.read_bytes()).hexdigest(),
                        'size': value.stat().st_size}
                  for key, value in files.items()},
    }
    (evidence / 'setup.json').write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding='utf-8')
    (storage.PROJECT_ROOT / '.sandbox/upload-run.txt').write_text(str(root), encoding='utf-8')
    print(root)


if __name__ == '__main__':
    main()
