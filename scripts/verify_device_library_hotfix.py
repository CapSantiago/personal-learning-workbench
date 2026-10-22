"""Read-only-image smoke check: all writes go to a disposable synthetic root."""
import asyncio
import gzip
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

sys.path.insert(0,str(Path.cwd()/'src'))
sys.path.insert(0,'/app/src')


async def verify():
    with tempfile.TemporaryDirectory(prefix='plw-reader-check-') as temp:
        root=Path(temp)/'data'
        os.environ['PLW_DATA_ROOT']=str(root)
        os.environ['PLW_BACKUP_ROOT']=str(Path(temp)/'backups')
        from starlette.applications import Starlette
        from streamlit.web.server.starlette.starlette_app import create_streamlit_middleware
        from plw import reader_runtime as readers, workspace
        from plw.private_auth import COOKIE, PrivateAccess, Session

        workspace.initialize_workspace(root)
        database=workspace.active_db(root)
        file=database.parent/'reading'/'synthetic.pdf'
        file.parent.mkdir()
        payload=b'%PDF-1.7\n'+bytes(range(256))*4096+b'\n%%EOF'
        file.write_bytes(payload)
        app=Starlette(routes=readers.reader_routes(),middleware=create_streamlit_middleware())
        owner=readers.ReaderAssets()
        edition=dict(id=str(uuid4()),pdf_relpath='reading/synthetic.pdf',
                     size_bytes=len(payload),pdf_sha256=hashlib.sha256(payload).hexdigest())
        owner.register(database,edition)
        gate=PrivateAccess(app,username='synthetic',origin='https://study.example.test',
                           password_digest='scrypt$'+'00'*16+'$'+'00'*64)
        gate.sessions['synthetic']=Session(time.monotonic()+600,'csrf',asyncio.Event())

        async def fetch(path,*,method='GET',auth=True,extra=()):
            headers=[(b'host',b'study.example.test'),(b'x-forwarded-proto',b'https'),
                     (b'origin',b'https://study.example.test'),*extra]
            if auth:headers.append((b'cookie',f'{COOKIE}=synthetic'.encode()))
            scope=dict(type='http',asgi={'version':'3.0','spec_version':'2.4'},
                       http_version='2',method=method,path=path,root_path='',query_string=b'',
                       scheme='http',headers=headers,server=('127.0.0.1',8501),client=('127.0.0.1',1234))
            messages=[]
            async def receive():return {'type':'http.request','body':b'','more_body':False}
            async def send(message):messages.append(message)
            await gate(scope,receive,send)
            first=next(m for m in messages if m['type']=='http.response.start')
            return first['status'],dict(first['headers']),b''.join(m.get('body',b'') for m in messages)

        url=owner.url+'/pdf/'+edition['id']+'.pdf'
        # The discovery GET must advertise the original length through the real
        # Streamlit middleware, not just through a bare Starlette router.
        code,headers,body=await fetch(url,extra=((b'accept-encoding',b'gzip'),))
        assert code==200 and body==payload
        assert headers.get(b'content-encoding',b'identity')==b'identity'
        assert int(headers[b'content-length'])==len(payload) and headers[b'accept-ranges']==b'bytes'
        code,headers,body=await fetch(url,extra=((b'range',b'bytes=0-65535'),(b'accept-encoding',b'gzip')))
        assert code==206 and body==payload[:65536]
        assert headers[b'content-range']==f'bytes 0-65535/{len(payload)}'.encode()
        assert headers[b'cache-control']==b'private, no-store' and headers.get(b'content-encoding',b'identity')==b'identity'
        code,headers,body=await fetch(url,extra=((b'range',f'bytes=4096-{len(payload)-1}'.encode()),))
        assert code==206 and body==payload[4096:]
        assert headers[b'content-range']==f'bytes 4096-{len(payload)-1}/{len(payload)}'.encode()
        assert int(headers[b'content-length'])==len(payload)-4096
        assert (await fetch(url,auth=False))[0]==401
        assert (await fetch(url,extra=((b'sec-fetch-site',b'cross-site'),)))[0]==403
        code,headers,body=await fetch(url,method='HEAD')
        assert code==200 and not body and headers[b'accept-ranges']==b'bytes'
        assert int(headers[b'content-length'])==len(payload)
        file.write_bytes(b'x'*len(payload))
        assert (await fetch(url,extra=((b'range',b'bytes=0-1'),)))[0]==409
        file.write_bytes(payload)
        vendor=owner.url+'/vendor/legacy/build/pdf.worker.mjs'
        code,headers,body=await fetch(vendor,extra=((b'accept-encoding',b'gzip'),))
        assert code==200 and headers[b'content-encoding']==b'gzip'
        original=(readers.ASSETS/'legacy/build/pdf.worker.mjs').read_bytes()
        assert gzip.decompress(body)==original and len(body)<len(original)*.5
        assert headers[b'cache-control']==b'private, no-store'
        compressed=len(body)
        code,headers,body=await fetch(vendor,extra=((b'accept-encoding',b'gzip;q=0'),))
        assert code==200 and body==original and headers.get(b'content-encoding',b'identity')==b'identity'
        from plw.services import LearningService
        from plw.materials import MaterialService
        service=LearningService(database)
        semester=service.create_semester('Synthetic',request_id=str(uuid4()))
        course=service.create_course(semester['id'],'Synthetic',request_id=str(uuid4()))
        MaterialService(database).import_upload(course['id'],'synthetic.pdf',payload,request_id=str(uuid4()))
        library=owner.register_library(database)
        code,headers,body=await fetch(library)
        import json
        manifest=json.loads(body)
        assert code==200 and manifest['run']==database.parent.name and len(manifest['files'])==1
        item=manifest['files'][0]
        code,headers,body=await fetch(item['url'])
        assert code==200 and body==payload and headers[b'content-encoding']==b'identity'
        assert (await fetch(library,auth=False))[0]==401
        for module,source in [('device-library.mjs','device_library.js'),('reader-module.mjs','reader.js')]:
            code,headers,body=await fetch(owner.url+'/'+module,extra=((b'accept-encoding',b'gzip'),))
            assert code==200 and gzip.decompress(body)==(readers.PROJECT/'src/plw/reader'/source).read_bytes()
            assert headers[b'cache-control']==b'private, no-store'
            assert (await fetch(owner.url+'/'+module,auth=False))[0]==401
        gate.sessions.clear()
        assert (await fetch(url))[0]==401
        print(f'READER FULL STACK CHECK PASSED: PDF discovery identity length {len(payload)}; range 65536 bytes; worker {len(original)} -> {compressed} bytes')




def verify_cache_sources():
    base=Path('/app/src/plw') if Path('/app/src/plw').exists() else Path.cwd()/'src/plw'
    js=(base/'reader/reader.js').read_text(encoding='utf-8')
    ui=(base/'ui_workbench.py').read_bytes()
    assert 'const READER_DOCUMENT_LIMIT=3,READER_BYTE_LIMIT=96*1024*1024;' in js
    assert 'const m=selectReaderModel(registry,data);' in js
    assert 'return readerDocument(m,async signal=>{' in js
    assert "'bytes':edition['size_bytes'],'digest':edition['pdf_sha256']".encode() in ui
    assert 'for(const [old,v] of registry){if(old!==key && !v.pending)' not in js
    assert "+'/vendor/legacy/build/pdf.mjs'" in js and "+'/vendor/legacy/build/pdf.worker.mjs'" in js
    assert 'return lib.getDocument({data:bytes,' in js
    assert "const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',output));" in js
    assert 'rangeChunkSize:65536' not in js
    assert 'model.downloadController?.abort()' in js
    assert 'await device.ensureDeviceFile(' in js
    assert b'def device_downloads(path):' in ui
    assert (base/'reader/device_library.js').exists() and (base/'reader/library_ui.js').exists()
    print('DEVICE DOWNLOAD LIBRARY SOURCE CONTRACT PASSED')

if __name__=='__main__':
    verify_cache_sources()
    asyncio.run(verify())
