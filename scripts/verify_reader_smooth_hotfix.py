"""Cloud image acceptance uses only a disposable synthetic dataset."""
import asyncio,json,os,tempfile,time,sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,'/app/src');sys.path.insert(0,str(Path.cwd()/'src'))

async def verify():
    with tempfile.TemporaryDirectory(prefix='plw-smooth-check-') as temp:
        root=Path(temp)/'data';os.environ['PLW_DATA_ROOT']=str(root);os.environ['PLW_BACKUP_ROOT']=str(Path(temp)/'backups')
        from plw import workspace,reader_runtime as readers
        from plw.services import LearningService
        from plw.materials import MaterialService
        from plw.workbench import Workbench
        from plw.private_auth import COOKIE,PrivateAccess,Session
        from starlette.applications import Starlette
        from streamlit.web.server.starlette.starlette_app import create_streamlit_middleware
        workspace.initialize_workspace(root);path=workspace.active_db(root);service=LearningService(path)
        semester=service.create_semester('Synthetic',request_id=str(uuid4()));course=service.create_course(semester['id'],'Synthetic',request_id=str(uuid4()))
        # Valid one-page PDF; no user files or network required.
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Contents 4 0 R >>',b'<< /Length 0 >>\nstream\nendstream']
        payload=bytearray(b'%PDF-1.4\n');offsets=[0]
        for n,obj in enumerate(objects,1):offsets.append(len(payload));payload.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
        xref=len(payload);payload.extend(b'xref\n0 5\n0000000000 65535 f \n')
        for offset in offsets[1:]:payload.extend(f'{offset:010d} 00000 n \n'.encode())
        payload.extend(f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        material=MaterialService(path).import_upload(course['id'],'synthetic.pdf',bytes(payload),request_id=str(uuid4()));w=Workbench(path);identity=w.create_edition(material['id'],str(uuid4()),local_copy_confirmed=True)
        app=Starlette(routes=readers.reader_routes(),middleware=create_streamlit_middleware());owner=readers.ReaderAssets();owner.register(path,w.rows('reading_editions')[0])
        gate=PrivateAccess(app,username='synthetic',origin='https://study.example.test',password_digest='scrypt$'+'00'*16+'$'+'00'*64)
        gate.sessions['synthetic']=Session(time.monotonic()+600,'csrf',asyncio.Event())
        action=dict(id=str(uuid4()),doc=identity,run=path.parent.name,page=1,base_revision=0,kind='mark',type='rectangle',points=[[.1,.2],[.3,.4]])
        async def post(value=action,auth=True,origin='https://study.example.test'):
            body=json.dumps(value).encode();messages=[];headers=[(b'host',b'study.example.test'),(b'x-forwarded-proto',b'https'),(b'origin',origin.encode()),(b'content-type',b'application/json')]
            if auth:headers.append((b'cookie',f'{COOKIE}=synthetic'.encode()))
            scope=dict(type='http',asgi={'version':'3.0'},http_version='1.1',method='POST',path=owner.url+'/action/'+identity,root_path='',query_string=b'',scheme='https',headers=headers,server=('study.example.test',443),client=('127.0.0.1',1234))
            async def receive():return dict(type='http.request',body=body,more_body=False)
            async def send(m):messages.append(m)
            await gate(scope,receive,send)
            return next(m['status'] for m in messages if m['type']=='http.response.start'),b''.join(m.get('body',b'') for m in messages)
        assert (await post(auth=False))[0]==401 and (await post(origin='https://invalid.example'))[0]==403
        for _ in range(2):
            code,body=await post();result=json.loads(body);assert code==200 and result['ack']==action['id'] and result['state']['revision']==1 and len(result['state']['marks'])==1
        assert (await post({**action,'id':str(uuid4())}))[0]==409
        print('READER BACKGROUND SAVE CHECK PASSED: authentication, cross-origin denial, real mark, identical retry and stale revision rejection')

if __name__=='__main__':asyncio.run(verify())
