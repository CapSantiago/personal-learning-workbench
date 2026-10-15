"""Local PDF tools and a capability-scoped, read-only asset server."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
import sys
from pathlib import Path
import subprocess
import threading
from urllib.parse import urlsplit,quote
from uuid import uuid4
from weakref import WeakValueDictionary

from . import db, storage, workspace, locking

PROJECT = Path(__file__).resolve().parents[2]
ASSETS = PROJECT/'assets'/'pdfjs'
PYTHON = Path(os.environ.get('PLW_PDF_PYTHON', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe') if os.name == 'nt' else sys.executable))

# The normal launcher installs public st.App routes before creating any reader.
# Direct `streamlit run app.py` retains the old loopback-only transport.
_same_origin = False
_readers = WeakValueDictionary()
_readers_lock = threading.RLock()


def _origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Invalid origin')
    return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == 'https' else 80)


def reader_routes():
    """Serve capability-scoped assets through Streamlit's public ASGI API.

    Relative URLs work behind one HTTPS reverse proxy. A future website login
    must protect the whole st.App (HTTP, uploads and WebSocket), not only its UI.
    The capability is an additional read boundary, not a replacement for login.
    """
    from starlette.responses import Response, FileResponse
    from starlette.routing import Route

    global _same_origin
    _same_origin = True

    def resource(request):
        try:
            origin = request.headers.get('origin')
            if (request.headers.get('sec-fetch-site') == 'cross-site'
                    or origin is not None and _origin(origin) != _origin(str(request.base_url))):
                return Response(status_code=403)
        except ValueError:
            return Response(status_code=403)
        with _readers_lock:
            owner = _readers.get(request.path_params['token'])
        if owner is None:
            return Response(status_code=404)
        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                 'Referrer-Policy':'no-referrer','Cross-Origin-Resource-Policy':'same-origin'}
        if request.path_params['resource'].startswith('media/'):
            status,file,mime=owner.media_resource(request.path_params['resource'])
            if status!=200:return Response(status_code=status,headers=headers)
            return FileResponse(file,media_type=mime,headers=headers)
        if request.path_params['resource'].startswith('download/'):
            status,record=owner.download_resource(request.path_params['resource'])
            if status!=200:return Response(status_code=status,headers=headers)
            return FileResponse(record['file'],media_type=record['mime'],filename=record['filename'],headers=headers)
        status, data, mime = owner._resource(request.path_params['resource'])
        return Response(data, status_code=status, media_type=mime, headers={
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'Cross-Origin-Resource-Policy': 'same-origin',
        })

    return [Route('/plw-reader/{token}/{resource:path}', resource, methods=['GET'])]


def inspect_pdf(path):
    result=subprocess.run([str(PYTHON),'-B','-X','utf8',str(PROJECT/'scripts/pdf_metadata.py'),str(path)],capture_output=True,text=True,encoding='utf-8',timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode: raise ValueError('PDF 无法读取或已加密，请先解锁或重新导出：'+result.stderr[-500:])
    return json.loads(result.stdout)


def convert_ppt(source,target):
    if os.name != 'nt' or os.environ.get('PLW_PRIVATE_SITE') == '1':
        raise ValueError('请在 Windows PowerPoint 导出 PDF，再上传为阅读版本。')
    try:
        result=subprocess.run([r'C:\Program Files\PowerShell\7\pwsh.exe','-NoProfile','-File',str(PROJECT/'scripts/convert_courseware.ps1'),'-Source',str(source),'-Target',str(target)],capture_output=True,text=True,encoding='utf-8',timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PowerPoint 转换超过两分钟。请检查 Office 窗口，手动导出 PDF 后通过“使用已导出的 PDF”继续。没有关闭你的 PowerPoint。') from exc
    if result.returncode or not target.exists():
        raise ValueError('PowerPoint 转换未完成，可手动导出 PDF 后继续。'+result.stderr[-500:])


class ReaderAssets:
    def __init__(self,origin=None):
        self.token=uuid4().hex+uuid4().hex
        self.documents={}
        self.media={}
        self.downloads={}
        self.lock=threading.RLock()
        self.vendor=json.loads((ASSETS/'manifest.json').read_text(encoding='utf-8'))
        self.server=None
        if _same_origin:
            with _readers_lock:
                _readers[self.token]=self
            self.url=f'/plw-reader/{self.token}'
            return
        if origin is None:
            import streamlit as st
            origin=f"http://127.0.0.1:{st.get_option('server.port')}"
        if _origin(origin)[:2] != ('http','127.0.0.1'):
            raise ValueError('Direct Streamlit launch supports loopback only. Use the PLW launcher for same-origin assets.')
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if self.headers.get('Origin') not in (None,origin): self.send_error(403);return
                prefix='/'+owner.token+'/'
                path=urlsplit(self.path).path
                if not path.startswith(prefix): self.send_error(404);return
                rel=path[len(prefix):]
                if rel.startswith('download/'):
                    if self.headers.get('Sec-Fetch-Site')=='cross-site':self.send_error(403);return
                    status,record=owner.download_resource(rel)
                    if status!=200:self.send_error(status);return
                    self.send_response(200)
                    self.send_header('Content-Type',record['mime']);self.send_header('Content-Length',str(record['size']))
                    self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(record['filename']))
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    self.end_headers()
                    with record['file'].open('rb') as source:
                        while chunk:=source.read(65536):self.wfile.write(chunk)
                    return
                if rel.startswith('media/'):
                    status,file,mime=owner.media_resource(rel)
                    if status!=200:self.send_error(status);return
                    size=file.stat().st_size;start,end=0,size-1
                    interval=self.headers.get('Range')
                    if interval:
                        import re
                        match=re.fullmatch(r'bytes=(\d*)-(\d*)',interval)
                        try:
                            if not match or not any(match.groups()):raise ValueError()
                            a,b=match.groups()
                            if a:start=int(a);end=min(int(b),size-1) if b else size-1
                            else:start=max(0,size-int(b))
                            if start>end or start>=size:raise ValueError()
                        except ValueError:
                            self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
                    self.send_response(206 if interval else 200)
                    self.send_header('Content-Type',mime);self.send_header('Content-Length',str(end-start+1))
                    self.send_header('Accept-Ranges','bytes');self.send_header('Access-Control-Allow-Origin',origin)
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    if interval:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    with file.open('rb') as source:
                        source.seek(start);remaining=end-start+1
                        while remaining:
                            chunk=source.read(min(65536,remaining))
                            if not chunk:break
                            self.wfile.write(chunk);remaining-=len(chunk)
                    return
                status,data,mime=owner._resource(rel)
                if status!=200: self.send_error(status);return
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
                self.send_header('Access-Control-Allow-Origin',origin);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
                self.end_headers();self.wfile.write(data)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/{self.token}'

    def _resource(self,rel):
        try:
            if rel.startswith('vendor/'):
                entry=rel[7:]
                if entry not in self.vendor: return 404,b'',None
                file=ASSETS/entry
                if any(p.is_symlink() or p.is_junction() for p in (file,*file.parents)):
                    raise ValueError('Invalid asset')
                data=file.read_bytes()
                if hashlib.sha256(data).hexdigest()!=self.vendor[entry]: raise ValueError('Asset changed')
            elif rel.startswith('pdf/') and rel.endswith('.pdf'):
                key=rel[4:-4]
                with self.lock: record=self.documents.get(key)
                if not record: return 404,b'',None
                database,file,digest=record
                root=locking.workspace_for(database)
                if root and workspace.active_db(root)!=database: return 410,b'',None
                storage.safe_path(file,must_exist=True,directory=False)
                data=file.read_bytes()
                if hashlib.sha256(data).hexdigest()!=digest: raise ValueError('Reading PDF changed')
            else: return 404,b'',None
            mime={'.mjs':'text/javascript','.js':'text/javascript','.pdf':'application/pdf','.wasm':'application/wasm','.css':'text/css'}.get(file.suffix,'application/octet-stream')
            return 200,data,mime
        except (OSError,ValueError,RuntimeError):
            return 409,b'',None

    def register(self,path,edition):
        file=storage.relative_file(Path(path).parent,edition['pdf_relpath'],must_exist=True)
        if storage.hash_file(file)!=(edition['size_bytes'],edition['pdf_sha256']): raise ValueError('阅读副本校验失败，请从完整备份恢复。')
        with self.lock:
            self.documents[edition['id']]=(Path(path),file,edition['pdf_sha256'])

    def register_download(self,path,material,edition=None):
        """Only managed originals or verified reading snapshots; never a client path."""
        import re
        database=Path(path)
        if material['deleted_at'] or material['import_state']!='ready':raise ValueError('课件暂不可下载。')
        if edition:
            if edition['material_id']!=material['id']:raise ValueError('阅读版本不属于此课件。')
            rel,size,digest=edition['pdf_relpath'],edition['size_bytes'],edition['pdf_sha256']
            suffix,mime='.pdf','application/pdf'
            identity=edition['id']
        else:
            if material['storage_mode']!='managed_copy' or material['file_deleted_at']:
                raise ValueError('原件只保存了外部路径，请先使用文件选择器导入完整课件。')
            rel,size,digest=material['managed_relpath'],material['size_bytes'],material['baseline_sha256']
            suffix=Path(rel).suffix.lower()
            mime={'.pdf':'application/pdf','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','.ppt':'application/vnd.ms-powerpoint'}.get(suffix,'application/octet-stream')
            identity=material['id']
        file=storage.relative_file(database.parent,rel,True)
        if storage.hash_file(file)!=(size,digest):raise ValueError('课件校验失败，已停止下载。')
        name=re.sub(r'[\x00-\x1f<>:"/\\|?*]','_',Path(material['name']).stem).strip(' .')[:140] or '课件'
        record=dict(database=database,file=file,size=size,digest=digest,mime=mime,filename=name+suffix,material=material['id'])
        key=hashlib.sha256((str(database)+identity+digest).encode()).hexdigest()
        with self.lock:self.downloads[key]=record
        return self.url+'/download/'+key

    def download_resource(self,rel):
        from .materials import MaterialService,MaterialError
        with self.lock:record=self.downloads.get(rel[9:]) if rel.startswith('download/') else None
        if not record:return 404,None
        try:
            database=record['database'];root=locking.workspace_for(database)
            if not root or workspace.active_db(root)!=database:return 410,None
            material=MaterialService(database).get_material(record['material'])
            if material['deleted_at'] or material['import_state']!='ready':return 410,None
            if storage.hash_file(record['file'])!=(record['size'],record['digest']):return 409,None
            return 200,record
        except (MaterialError,OSError,ValueError,RuntimeError):return 409,None

    def register_media(self,path,edition_id,item):
        database=Path(path)
        with self.lock:edition=self.documents.get(edition_id)
        if not edition or edition[0]!=database:raise ValueError('请先注册当前阅读版本。')
        root=locking.workspace_for(database)
        scope=root/'cache'/database.parent.name/'media'/edition_id if root else None
        if scope is None:raise ValueError('媒体需要独立学习库。')
        file=storage.safe_path(Path(item['path']),root=scope,must_exist=True,directory=False)
        if item['mime'] not in ('video/mp4','video/webm'):raise ValueError('此视频格式暂不能在浏览器中播放。')
        if storage.hash_file(file)!=(item['size_bytes'],item['sha256']):raise ValueError('视频副本校验失败，请重新生成。')
        key=hashlib.sha256((str(database)+edition_id+item['sha256']).encode()).hexdigest()+('.mp4' if item['mime']=='video/mp4' else '.webm')
        with self.lock:self.media[key]=(database,file,item['size_bytes'],item['sha256'],item['mime'])
        return self.url+'/media/'+key

    def media_resource(self,rel):
        with self.lock:record=self.media.get(rel[6:]) if rel.startswith('media/') else None
        if not record:return 404,None,None
        database,file,size,digest,mime=record
        try:
            root=locking.workspace_for(database)
            if not root or workspace.active_db(root)!=database:return 410,None,None
            storage.safe_path(file,must_exist=True,directory=False)
            if storage.hash_file(file)!=(size,digest):raise ValueError('Video changed')
            return 200,file,mime
        except (OSError,ValueError,RuntimeError):return 409,None,None

