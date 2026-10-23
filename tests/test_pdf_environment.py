"""Real PDF subprocess and managed import checks; synthetic bytes only."""
from io import BytesIO
from pathlib import Path
import hashlib,json,os,subprocess,sys
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pypdf import PdfReader,PdfWriter
from plw import reader_runtime as reader,storage,workspace
from plw.services import LearningService
from plw.materials import MaterialService
from plw.uploads import import_courseware


def payload(password=None,algorithm='RC4-128'):
    writer=PdfWriter();writer.add_blank_page(width=600,height=400)
    if password is not None:writer.encrypt(password,owner_password='synthetic-owner',algorithm=algorithm)
    stream=BytesIO();writer.write(stream);return stream.getvalue()


@pytest.mark.parametrize('password,algorithm',[(None,'RC4-128'),('','RC4-128'),('','AES-128'),('','AES-256')])
def test_readable_pdf_import_preserves_original_and_reuses_saved_material(password,algorithm):
    root=storage.ROOTS[1]/('pdf-permissions-'+str(uuid4()));workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('Synthetic',request_id=str(uuid4()))
    course=service.create_course(semester['id'],'Synthetic',request_id=str(uuid4()))
    body=payload(password,algorithm);parsed=PdfReader(BytesIO(body))
    if password is not None:assert parsed.is_encrypted
    first=import_courseware(path,course['id'],[('synthetic.pdf',body)],str(uuid4()))[0]
    assert first['status']=='ready',first['message']
    material=MaterialService(path).get_material(first['material_id'])
    assert (path.parent/material['managed_relpath']).read_bytes()==body
    again=import_courseware(path,course['id'],[('synthetic.pdf',body)],str(uuid4()))[0]
    assert again['reused'] and again['material_id']==first['material_id'] and again['edition_id']==first['edition_id']


def test_password_required_upload_is_retained_without_claiming_success():
    root=storage.ROOTS[1]/('pdf-password-'+str(uuid4()));workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    semester=service.create_semester('Synthetic',request_id=str(uuid4()));course=service.create_course(semester['id'],'Synthetic',request_id=str(uuid4()))
    body=payload('known-test-password','AES-256')
    row=import_courseware(path,course['id'],[('locked.pdf',body)],str(uuid4()))[0]
    assert row['status']=='saved' and '需要打开密码' in row['message'] and row['edition_id'] is None
    material=MaterialService(path).get_material(row['material_id'])
    assert (path.parent/material['managed_relpath']).read_bytes()==body


def test_default_python_has_no_codex_dependency():
    env=os.environ.copy();env.pop('PLW_PDF_PYTHON',None)
    env['PYTHONPATH']=str(storage.PROJECT_ROOT/'src')
    result=subprocess.run([sys.executable,'-c','from plw.reader_runtime import PYTHON;import sys;assert str(PYTHON)==sys.executable'],env=env,capture_output=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('stderr,expected',[("No module named 'pypdf'",'缺少 pypdf'),('cryptography is required for AES algorithm','缺少 cryptography'),('SyntaxError: synthetic','不能据此判断文件已加密')])
def test_environment_failures_are_not_misreported_as_locked_pdfs(monkeypatch,stderr,expected):
    monkeypatch.setattr(reader.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr=stderr))
    with pytest.raises(ValueError,match=expected):reader.inspect_pdf(Path('synthetic.pdf'))
