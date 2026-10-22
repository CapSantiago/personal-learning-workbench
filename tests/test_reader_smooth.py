"""Real scoped save endpoint, revision/idempotency and dataset/auth boundaries."""
import asyncio,json,sys,time
from pathlib import Path
from uuid import uuid4
import pytest
from starlette.applications import Starlette
from streamlit.web.server.starlette.starlette_app import create_streamlit_middleware
from plw import reader_runtime as readers,storage,workspace,backups
from plw.services import LearningService
from plw.materials import MaterialService
from plw.workbench import Workbench
from plw.private_auth import COOKIE,PrivateAccess,Session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reader_navigation_seed import pdf_bytes

@pytest.fixture
def reader_save():
    root=storage.ROOTS[1]/('reader-smooth-'+str(uuid4()));workspace.initialize_workspace(root)
    path=workspace.active_db(root);service=LearningService(path)
    sem=service.create_semester('合成保存测试',request_id=str(uuid4()))
    course=service.create_course(sem['id'],'合成课件',request_id=str(uuid4()))
    material=MaterialService(path).import_upload(course['id'],'synthetic.pdf',pdf_bytes([(960,540,0,None)]*8),request_id=str(uuid4()))
    w=Workbench(path);identity=w.create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
    app=Starlette(routes=readers.reader_routes(),middleware=create_streamlit_middleware());owner=readers.ReaderAssets()
    owner.register(path,w.rows('reading_editions')[0])
    gate=PrivateAccess(app,username='synthetic',origin='https://plw.example',password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic']=Session(time.monotonic()+600,'csrf',asyncio.Event())
    return root,path,w,owner,gate,dict(id=str(uuid4()),run=path.parent.name,doc=identity,page=2,base_revision=0,kind='position')

def post(fixture,value=None,*,origin='https://plw.example',auth=True,token=None,doc=None,mime='application/json',raw=None):
    _,_,_,owner,app,action=fixture
    data=raw if raw is not None else json.dumps(value or action).encode();messages=[]
    url=f'/plw-reader/{token or owner.token}/action/{doc or action["doc"]}'
    headers=[(b'host',b'plw.example'),(b'x-forwarded-proto',b'https'),(b'content-type',mime.encode())]
    if origin is not None:headers.append((b'origin',origin.encode()))
    if auth:headers.append((b'cookie',f'{COOKIE}=synthetic'.encode()))
    scope=dict(type='http',asgi={'version':'3.0'},http_version='1.1',scheme='https',method='POST',path=url,root_path='',query_string=b'',headers=headers,server=('plw.example',443),client=('127.0.0.1',1234))
    async def receive():return dict(type='http.request',body=data,more_body=False)
    async def send(message):messages.append(message)
    asyncio.run(app(scope,receive,send))
    first=next(m for m in messages if m['type']=='http.response.start');body=b''.join(m.get('body',b'') for m in messages)
    return first['status'],dict(first['headers']),body

def test_background_save_is_idempotent_returns_state_and_never_hashes_pdf(reader_save,monkeypatch):
    _,_,w,_,_,action=reader_save
    monkeypatch.setattr(storage,'hash_file',lambda *_:pytest.fail('Saving must not reread the PDF'))
    for _ in range(2):
        code,headers,body=post(reader_save);result=json.loads(body)
        assert code==200 and result['ack']==action['id'] and result['state']==dict(page=2,revision=1,marks=[])
        assert headers[b'cache-control']==b'private, no-store'
    assert w.edition_state(action['doc'])['revision']==1

def test_mark_undo_redo_and_stale_revision_protection(reader_save):
    *_,action=reader_save
    mark={**action,'kind':'mark','type':'rectangle','points':[[.1,.2],[.4,.6]]}
    assert post(reader_save,mark)[0]==200
    stale={**action,'id':str(uuid4()),'page':4}
    assert post(reader_save,stale)[0]==409
    undo={**stale,'kind':'undo','base_revision':1}
    assert json.loads(post(reader_save,undo)[2])['state']['marks']==[]
    redo={**undo,'id':str(uuid4()),'kind':'redo','base_revision':2}
    result=json.loads(post(reader_save,redo)[2]);assert result['state']['marks'][0]['id']==mark['id']

@pytest.mark.parametrize('kwargs,expected',[
    ({'auth':False},401),({'origin':'https://evil.example'},403),({'origin':None},403),
    ({'token':'unknown'},404),({'doc':str(uuid4())},404),({'mime':'text/plain'},415),
    ({'raw':b'not json'},400),({'raw':b'x'*200001},413),
])
def test_save_request_boundaries(reader_save,kwargs,expected):assert post(reader_save,**kwargs)[0]==expected

def test_doc_and_dataset_are_bound_to_registration(reader_save):
    *_,action=reader_save
    assert post(reader_save,{**action,'doc':str(uuid4())})[0]==400
    assert post(reader_save,{**action,'run':'other-dataset'})[0]==400

def test_restored_dataset_revokes_old_writer(reader_save):
    root,path,*_=reader_save
    backup=backups.create_backup(path);backups.restore_backup(root,backup['path'],confirmation=path.parent.name)
    assert post(reader_save)[0]==410
