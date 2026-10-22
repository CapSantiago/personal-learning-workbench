"""Disposable AppTest checks for the shipped private-site layout."""
from pathlib import Path
from uuid import uuid4
import os,tempfile,sys
sys.path.insert(0,'/app/src');sys.path.insert(0,str(Path.cwd()/'src'))
with tempfile.TemporaryDirectory(prefix='plw-workspace-ui-') as folder:
 root=Path(folder)/'data';os.environ['PLW_DATA_ROOT']=str(root);os.environ['PLW_BACKUP_ROOT']=str(Path(folder)/'backups');os.environ['PLW_WORKSPACE']=str(root);os.environ['PLW_PRIVATE_SITE']='1'
 from plw import workspace
 from plw.services import LearningService
 from streamlit.testing.v1 import AppTest
 workspace.initialize_workspace(root);db=workspace.active_db(root);service=LearningService(db)
 sem=service.create_semester('Synthetic',request_id=str(uuid4()));courses=[service.create_course(sem['id'],'Synthetic '+str(n),request_id=str(uuid4())) for n in range(7)]
 archived=service.create_course(sem['id'],'Archived synthetic',request_id=str(uuid4()));service.set_course_archived(archived['id'],True,archived['revision'])
 source=Path('/app/app.py') if Path('/app/app.py').exists() else Path.cwd()/'app.py'
 page=AppTest.from_file(str(source),default_timeout=30).run()
 assert not page.exception and not page.error
 keys=[item.key for item in page.button if item.key and item.key.startswith('home_course_')]
 assert keys==['home_course_'+row['id'] for row in courses]
 page.button(key='home_course_'+courses[-1]['id']).click().run()
 assert not page.exception and not page.error and page.session_state['_selected_course']==courses[-1]['id']
 assert any(item.value==courses[-1]['name'] for item in page.header)
 print('READING WORKSPACE UI CHECK PASSED: all seven active courses, archived exclusion, last-course navigation and empty shelf tools')
