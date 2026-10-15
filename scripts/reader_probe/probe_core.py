"""Isolated R0 experiment: allowlisted assets and durable synthetic annotations."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import uuid

PROJECT = Path(__file__).resolve().parents[2]
BASE = PROJECT/'.sandbox/r0'

def confined(path: Path, root: Path) -> Path:
    if not path.is_absolute() or not path.is_relative_to(root):
        raise ValueError('Path outside synthetic run')
    for p in [path,*path.parents]:
        if p.is_symlink() or p.is_junction(): raise ValueError('Links are not permitted')
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Path escapes synthetic run')
    if path.exists() and path.is_file() and path.stat().st_nlink!=1:
        raise ValueError('Hard links are not permitted')
    return path

def run_root(run_id: str) -> Path:
    if str(uuid.UUID(run_id))!=run_id: raise ValueError('Invalid run ID')
    root=confined(BASE/run_id,BASE)
    if not (root/'fixtures.json').is_file(): raise ValueError('Run not prepared')
    return root

def read_json(path): return json.loads(path.read_text(encoding='utf-8-sig'))

def atomic_json(path, value):
    confined(path,BASE)
    temp=path.with_name(path.name+'.'+str(uuid.uuid4())+'.tmp')
    with temp.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def catalog(root):
    result=list(read_json(root/'fixtures.json')['files'])
    for path in sorted((root/'converted').glob('*.pdf')):
        result.append({'id':path.stem,'name':path.name+'（PPT 转换）','path':str(path.relative_to(root)),
            'kind':'converted','pages':4,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    for d in result:
        p=confined(root/d['path'],root)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=d['sha256']: raise ValueError('Fixture changed')
    return result

class ProbeStore:
    def __init__(self,root):
        self.root=root; self.path=root/'annotations.json'; self.lock=threading.RLock()
    def read(self):
        return read_json(self.path) if self.path.exists() else {'revision':0,'ops':{},'documents':{}}
    def document(self,doc):
        return self.read()['documents'].get(doc,{'marks':[],'page':1})
    def apply(self,action,documents,fail=False):
        with self.lock:
            state=self.read()
            if not isinstance(action,dict) or len(json.dumps(action))>200_000:raise ValueError('Invalid operation')
            op=action.get('id'); uuid.UUID(op)
            payload_hash=hashlib.sha256(json.dumps(action,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if op in state['ops']:
                if state['ops'][op]!=payload_hash: raise ValueError('Operation ID reused with different content')
                return state
            if action.get('run')!=self.root.name: raise ValueError('Stale dataset')
            if action.get('base_revision')!=state['revision']: raise ValueError('Revision conflict')
            doc=documents.get(action.get('doc'))
            if not doc: raise ValueError('Unknown document edition')
            page=action.get('page')
            if type(page)!=int or not 1<=page<=doc['pages']:raise ValueError('Invalid page')
            value=state['documents'].setdefault(doc['sha256'],{'marks':[],'page':1})
            if action.get('kind')=='mark':
                kind=action.get('type')
                if kind not in ['ink','rectangle','highlight']:raise ValueError('Unknown geometry')
                pts=action.get('points')
                if not isinstance(pts,list) or not 2<=len(pts)<=4096:raise ValueError('Invalid points')
                for p in pts:
                    if not isinstance(p,list) or len(p)!=2:raise ValueError('Invalid point')
                    for n in p:
                        if type(n) not in [int,float] or not math.isfinite(n) or not 0<=n<=1:raise ValueError('Invalid coordinate')
                value['marks'].append({'id':op,'type':kind,'page':page,'points':pts})
            elif action.get('kind')!='position':raise ValueError('Unknown action')
            value['page']=page
            state['revision']+=1;state['ops'][op]=payload_hash
            if fail:raise OSError('合成故障：未写入磁盘，请重试')
            atomic_json(self.path,state)
            return state

class Assets:
    def __init__(self,root,docs,port=8504):
        self.token=uuid.uuid4().hex
        self.url=f'http://127.0.0.1:{port}/{self.token}'
        vendor=read_json(root/'vendor-manifest.json')['files']
        file_map={f'/pdf/{d["sha256"]}.pdf':(root/d['path'],d['sha256']) for d in docs}
        file_map['/pdf/broken.pdf']=(root/'sources/损坏.pdf',None)
        for rel,digest in vendor.items():file_map['/vendor/'+rel.replace('\\','/')]=(root/'vendor'/rel,digest)
        token=self.token
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                target=unquote(urlsplit(self.path).path)
                key=target.removeprefix('/'+token)
                if not target.startswith('/'+token+'/') or key not in file_map:
                    self.send_error(404);return
                if self.headers.get('Origin') not in [None,'http://127.0.0.1:8503']:
                    self.send_error(403);return
                try:
                    path,expected=file_map[key];data=confined(path,root).read_bytes()
                    if expected and hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Asset changed')
                except (OSError,ValueError):self.send_error(409);return
                suffix=path.suffix
                mime={'.mjs':'text/javascript','.js':'text/javascript','.pdf':'application/pdf','.wasm':'application/wasm'}.get(suffix,'application/octet-stream')
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
                self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:8503');self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers();self.wfile.write(data)
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

