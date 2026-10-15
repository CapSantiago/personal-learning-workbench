"""Only synthetic fixtures; invoked after browser confirms its test workspace."""
from pathlib import Path
import json
import shutil
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from plw import workspace,storage
from plw.services import LearningService

root=Path(sys.argv[1])
assert root.is_relative_to(storage.ROOTS[1]) and root!=storage.ROOTS[1]
path=workspace.active_db(root)
s=LearningService(path)
if not s.list_semesters():
    sem=s.create_semester('2026 秋 · 合成验收',request_id=str(uuid4()))
    s.create_course(sem['id'],'控制原理 · 合成验收',request_id=str(uuid4()))
fixtures=storage.PROJECT_ROOT/'.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'
sources=root/'sources';sources.mkdir(exist_ok=True)
for name in ('原生 PDF 中文课件.pdf','宽屏 合成课件.pptx','旧格式 合成课件.ppt'):
    target=sources/name
    if not target.exists():shutil.copyfile(fixtures/name,target)
print(json.dumps({'course':s.list_courses()[0]['id'],'path':str(path)},ensure_ascii=False))
