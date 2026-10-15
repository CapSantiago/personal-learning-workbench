"""Create synthetic fixtures for the 0.2.2 interface acceptance; never production."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from plw import storage,workspace
from plw.services import LearningService
from plw.materials import MaterialService
from plw.workbench import Workbench

root=storage.ROOTS[1]/('ui-polish-'+str(uuid4()))
workspace.initialize_workspace(root)
path=workspace.active_db(root);service=LearningService(path);w=Workbench(path)
semester=service.create_semester('2026 秋季',request_id=str(uuid4()))
courses=[service.create_course(semester['id'],name,teacher=teacher,request_id=str(uuid4())) for name,teacher in [('自动控制原理','陈老师'),('机器人学','李老师'),('高等数学','王老师')]]
sources=root/'sources';sources.mkdir()
fixtures=storage.PROJECT_ROOT/'.sandbox/r0/968c198e-a06e-4438-8910-6cf634af2c15/sources'
editions={}
for name in ('原生 PDF 中文课件.pdf','旋转 裁剪.pdf','图片型 PDF.pdf','性能 300页.pdf'):
    source=sources/name;shutil.copyfile(fixtures/name,source)
    material=MaterialService(path).import_file(courses[0]['id'],str(source),'managed_copy',request_id=str(uuid4()))
    edition=w.create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
    editions[name]=edition
    if name=='原生 PDF 中文课件.pdf':
        state=w.edition_state(edition)
        w.reader_action({'id':str(uuid4()),'run':path.parent.name,'doc':edition,'page':2,'base_revision':state['revision'],'kind':'position'})
today=datetime.now(timezone(timedelta(hours=8))).date()
for name,offset,kind in [('完成第二章习题',0,'assignment'),('准备闭环控制实验',2,'lab'),('复习拉普拉斯变换',-1,'review')]:
    w.save_task(courses[0]['id'],dict(title=name,task_type=kind,due_kind='date',due_date=(today+timedelta(days=offset)).isoformat(),due_at_utc=None,due_timezone=None,planned_date=today.isoformat(),priority='normal',status='todo',estimated_minutes=30,actual_minutes=0,remarks=''),[],str(uuid4()))
w.save_note(courses[0]['id'],'反馈与稳定性','# 闭环控制\n\n负反馈帮助系统减小误差。\n\n$$G(s)=\\frac{1}{s+1}$$',None,[],str(uuid4()))
evidence=root/'evidence';evidence.mkdir()
(evidence/'setup.json').write_text(json.dumps({'root':str(root),'editions':editions,'courses':[c['id'] for c in courses]},ensure_ascii=False,indent=2),encoding='utf-8')
(storage.PROJECT_ROOT/'.sandbox/ui-polish-run.txt').write_text(str(root),encoding='utf-8')
print(root)
