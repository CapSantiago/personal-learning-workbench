"""Cloud acceptance: only temporary learning data and accent preferences."""
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

sys.path[:0]=['/app/src',str(Path.cwd()/'src')]
with tempfile.TemporaryDirectory(prefix='plw-appearance-check-') as folder:
    root=Path(folder)/'data'
    os.environ.update(PLW_DATA_ROOT=str(root),PLW_BACKUP_ROOT=str(Path(folder)/'backups'),PLW_WORKSPACE=str(root),PLW_PRIVATE_SITE='1')
    from plw import workspace,ui_theme
    from plw.services import LearningService
    from streamlit.testing.v1 import AppTest
    workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('Synthetic',request_id=str(uuid4()))
    service.create_course(semester['id'],'Synthetic',request_id=str(uuid4()))
    before=(path.read_bytes(),(path.parent/'config.json').read_bytes(),(root/'control/active.json').read_bytes())
    ui_theme.save_theme(root,'purple')
    assert before==(path.read_bytes(),(path.parent/'config.json').read_bytes(),(root/'control/active.json').read_bytes())
    source=Path('/app/app.py') if Path('/app/app.py').exists() else Path.cwd()/'app.py'
    page=AppTest.from_file(str(source),default_timeout=30).run()
    assert not page.exception and page.session_state['_plw_theme']=='purple'
    page.button(key='nav_外观设置').click().run()
    page.selectbox(key='theme_choice').select('yellow')
    next(button for button in page.button if button.label=='保存主题颜色').click().run()
    assert not page.exception and not page.error and ui_theme.load_theme(root)=='yellow'
    page=AppTest.from_file(str(source),default_timeout=30).run()
    assert not page.exception and page.session_state['_plw_theme']=='yellow'
    assert len(service.list_courses())==1
    print('APPEARANCE UI CHECK PASSED: persistent accent, fresh session, unchanged learning data and native settings form')
