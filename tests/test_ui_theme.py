"""Accent persistence is separate from the learning schema and full backup."""
from pathlib import Path
from uuid import uuid4
import hashlib
import json

import pytest
from streamlit.testing.v1 import AppTest

from plw import backups, storage, workspace, ui_theme
from plw.services import LearningService


@pytest.fixture
def root(monkeypatch):
    root=storage.ROOTS[1]/('ui-theme-'+str(uuid4()))
    workspace.initialize_workspace(root)
    monkeypatch.setenv('PLW_WORKSPACE',str(root))
    monkeypatch.setenv('PLW_PRIVATE_SITE','1')
    return root


def test_theme_survives_new_session_and_does_not_touch_learning_data(root):
    path=workspace.active_db(root)
    service=LearningService(path)
    semester=service.create_semester('Synthetic',request_id=str(uuid4()))
    service.create_course(semester['id'],'Synthetic course',request_id=str(uuid4()))
    before=(path.read_bytes(),(root/'control/active.json').read_bytes(),(path.parent/'config.json').read_bytes())
    assert ui_theme.load_theme(root)=='green'
    ui_theme.save_theme(root,'purple')
    assert ui_theme.load_theme(root)=='purple'
    assert before==(path.read_bytes(),(root/'control/active.json').read_bytes(),(path.parent/'config.json').read_bytes())
    result=backups.create_backup(path)
    assert result['complete'] is True
    assert len(service.list_courses())==1
    # A fresh AppTest has no previous Streamlit session state to mask a missing file.
    page=AppTest.from_file(str(storage.PROJECT_ROOT/'app.py'),default_timeout=30).run()
    assert not page.exception and page.session_state['_plw_theme']=='purple'
    page.button(key='nav_外观设置').click().run()
    assert not page.exception and page.selectbox(key='theme_choice').value=='purple'
    page.selectbox(key='theme_choice').select('yellow')
    next(b for b in page.button if b.label=='保存主题颜色').click().run()
    assert not page.exception and not page.error and ui_theme.load_theme(root)=='yellow'
    page=AppTest.from_file(str(storage.PROJECT_ROOT/'app.py'),default_timeout=30).run()
    assert page.session_state['_plw_theme']=='yellow'
    page.button(key='nav_外观设置').click().run()
    next(b for b in page.button if b.label=='恢复默认绿色').click().run()
    assert not page.exception and ui_theme.load_theme(root)=='green'


@pytest.mark.parametrize('value',['<style>','../purple',None,[],{'color':'red'}])
def test_invalid_theme_cannot_replace_the_saved_preference(root,value):
    ui_theme.save_theme(root,'black')
    file=root/'control/ui-preferences.json';before=file.read_bytes()
    with pytest.raises(ValueError):ui_theme.save_theme(root,value)
    assert file.read_bytes()==before


@pytest.mark.parametrize('value',[{'version':True,'accent':'blue'},{'version':1,'accent':[]},{'version':1,'accent':'#111'},[]])
def test_corrupt_preferences_fall_back_without_being_silently_overwritten(root,value):
    file=root/'control/ui-preferences.json';file.write_text(json.dumps(value),encoding='utf-8')
    before=file.read_bytes()
    with pytest.raises(ValueError):ui_theme.load_theme(root)
    page=AppTest.from_file(str(storage.PROJECT_ROOT/'app.py'),default_timeout=30).run()
    assert not page.exception and page.session_state['_plw_theme']=='green'
    assert file.read_bytes()==before


def luminance(hex_color):
    channels=[int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
    channels=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))


def contrast(a,b):
    values=sorted([luminance(a),luminance(b)])
    return (values[1]+.05)/(values[0]+.05)


@pytest.mark.parametrize('name',list(ui_theme.PALETTES))
def test_presets_keep_text_and_controls_readable_without_recoloring_background(name):
    p=ui_theme.PALETTES[name]
    assert contrast(p['text'],p['accent'])>=4.5
    assert contrast(p['text'],p['hover'])>=4.5
    assert contrast(p['ink'],p['soft'])>=4.5
    assert contrast(p['control'],'#ffffff')>=3
    css=ui_theme.theme_css(name)
    assert '--plw-bg:' not in css and '--plw-sidebar:' not in css and '--plw-surface:' not in css
