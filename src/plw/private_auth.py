"""Single-owner ASGI gate covering HTTP, uploads, downloads and live WebSockets.

Sessions are process-local: run one worker. Restarting revokes every session.
"""
import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
import hashlib
import hmac
from html import escape
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.gzip import GZipMiddleware
from starlette.datastructures import Headers, MutableHeaders

from plw.private_assets import accepts_gzip, cacheable_asset_response, versioned_asset_request

COOKIE='plw_private_session'


def password_hash(password):
    if not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError('密码须为 12–256 个字符。')
    salt=secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=131072,r=8,p=1,maxmem=256*1024*1024)
    return f'scrypt${salt.hex()}${digest.hex()}'


def validate_hash(value):
    try:
        name,salt,digest=value.split('$')
        if name!='scrypt' or len(salt)!=32 or len(digest)!=128:raise ValueError()
        return bytes.fromhex(salt),bytes.fromhex(digest)
    except (AttributeError,TypeError,ValueError) as exc:
        raise ValueError('登录密码校验值无效，请重新运行设置工具。') from exc


def verify_password(password,value):
    salt,expected=validate_hash(value)
    if not isinstance(password,str) or len(password)>256:return False
    actual=hashlib.scrypt(password.encode(),salt=salt,n=131072,r=8,p=1,maxmem=256*1024*1024)
    return hmac.compare_digest(actual,expected)


@dataclass
class Session:
    expires:float
    csrf:str
    revoked:asyncio.Event


class PrivateAccess:
    def __init__(self,app,*,username,password_digest,origin,preview=False,ttl=43200,health_check=None):
        parsed=urlsplit(origin)
        if (parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or parsed.scheme!='https' and not (preview and parsed.hostname=='127.0.0.1')):
            raise ValueError('正式网站必须配置不带路径的 HTTPS 地址。')
        validate_hash(password_digest)
        if not isinstance(username,str) or not 1<=len(username)<=80:raise ValueError('账号名称无效。')
        self.app=app;self.username=username;self.digest=password_digest;self.origin=origin
        self.authority=parsed.netloc;self.secure=parsed.scheme=='https';self.ttl=ttl
        self.sessions={};self.attempts=deque();self.checking=False
        self.form_secret=secrets.token_bytes(32)
        self.health_check=health_check
        self.compressed_assets=GZipMiddleware(app,minimum_size=1024,compresslevel=5)

    def _form_token(self):
        stamp=str(int(time.time()))
        return stamp+'.'+hmac.new(self.form_secret,stamp.encode(),hashlib.sha256).hexdigest()

    def _valid_form(self,value):
        try:
            stamp,signature=value.split('.')
            return (0<=time.time()-int(stamp)<=900 and hmac.compare_digest(signature,hmac.new(self.form_secret,stamp.encode(),hashlib.sha256).hexdigest()))
        except (TypeError,ValueError):return False

    def _session(self,connection):
        now=time.monotonic()
        for key,item in list(self.sessions.items()):
            if item.expires<=now:item.revoked.set();del self.sessions[key]
        return self.sessions.get(connection.cookies.get(COOKIE,''))

    def _page(self,body,status=200):
        return HTMLResponse('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PLW · 私人学习工作台</title><style>
body{margin:0;background:#f6f8f6;color:#243b35;font:16px system-ui,sans-serif;display:grid;min-height:100dvh;place-items:center}main{box-sizing:border-box;width:min(420px,calc(100% - 32px));padding:32px;background:white;border:1px solid #dce5de;border-radius:16px}h1{margin-top:0;font-size:28px}p{line-height:1.6;color:#53675e}label{display:block;margin:18px 0 6px}input,button{box-sizing:border-box;width:100%;padding:12px;font:inherit;border:1px solid #ccd9d1;border-radius:8px}button{background:#25665c;color:white;margin-top:24px;cursor:pointer}a{color:#25665c}.error{color:#893b32}</style><main>'''+body+'</main></html>',status_code=status,headers={
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin',
            'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})

    def login_page(self,error='',status=200):
        return self._page('<h1>PLW</h1><p>登录你的私人学习工作台</p>'
            +('<p class="error" role="alert">'+escape(error)+'</p>' if error else '')
            +'<form method="post" action="/plw-auth/login"><input type="hidden" name="csrf" value="'+self._form_token()+'">'
            '<label for="username">账号</label><input id="username" name="username" autocomplete="username" required maxlength="80">'
            '<label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="256">'
            '<button type="submit">登录</button></form><p>课件保存到设备后可离线阅读。</p>',status)

    async def _fields(self,scope,receive):
        if not dict(scope['headers']).get(b'content-type',b'').startswith(b'application/x-www-form-urlencoded'):
            raise ValueError('Unsupported form')
        content=b''
        async with asyncio.timeout(10):
            while True:
                message=await receive()
                if message['type']=='http.disconnect':raise ValueError('Disconnected')
                content+=message.get('body',b'')
                if len(content)>4096:raise ValueError('Form too large')
                if not message.get('more_body',False):break
        values=parse_qs(content.decode('utf-8'),max_num_fields=5,strict_parsing=True)
        if any(len(v)!=1 for v in values.values()):raise ValueError('Duplicate field')
        return {k:v[0] for k,v in values.items()}

    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'):
            return await self.app(scope,receive,send)
        connection=HTTPConnection(scope)
        if (self.health_check and scope['type']=='http' and scope.get('method')=='GET'
                and scope.get('path')=='/plw-health'
                and scope.get('client',('',0))[0] in ('127.0.0.1','::1')
                and connection.headers.get('host','').split(':',1)[0]=='127.0.0.1'):
            from starlette.responses import JSONResponse
            try:
                response=JSONResponse(await asyncio.to_thread(self.health_check),headers={'Cache-Control':'no-store'})
            except Exception:
                response=JSONResponse({'ok':False},status_code=503,headers={'Cache-Control':'no-store'})
            return await response(scope,receive,send)
        # The trusted loopback proxy replaces Host and X-Forwarded-Proto.
        valid_host=connection.headers.get('host')==self.authority
        scheme=scope.get('scheme') in ('https','wss')
        valid_transport=not self.secure or scheme or connection.headers.get('x-forwarded-proto')=='https'
        supplied_origin=connection.headers.get('origin')
        cross_site=connection.headers.get('sec-fetch-site')=='cross-site'
        # A normal external link may open only the entry/login document. It must
        # still pass login; cross-site API, file, frame and write requests stay denied.
        entry_navigation=(scope['type']=='http' and scope.get('method')=='GET'
            and scope.get('path') in ('/','/plw-auth/login')
            and connection.headers.get('sec-fetch-mode')=='navigate'
            and connection.headers.get('sec-fetch-dest')=='document'
            and supplied_origin is None)
        if (not valid_host or not valid_transport or cross_site and not entry_navigation
                or supplied_origin not in (None,self.origin)):
            if scope['type']=='websocket':return await send({'type':'websocket.close','code':1008})
            return await Response('Forbidden',status_code=403)(scope,receive,send)
        if self.secure:
            scope={**scope,'scheme':'wss' if scope['type']=='websocket' else 'https'}
        session=self._session(connection)
        if scope['type']=='websocket':
            if not session or supplied_origin!=self.origin:
                return await send({'type':'websocket.close','code':1008})
            running=asyncio.create_task(self.app(scope,receive,send))
            revoked=asyncio.create_task(session.revoked.wait())
            try:
                done,_=await asyncio.wait((running,revoked),timeout=max(0,session.expires-time.monotonic()),return_when=asyncio.FIRST_COMPLETED)
                if running in done:return await running
                running.cancel()
                with suppress(asyncio.CancelledError):await running
                await send({'type':'websocket.close','code':4001})
            finally:
                for task in (running,revoked):
                    if not task.done():task.cancel()
                await asyncio.gather(running,revoked,return_exceptions=True)
            return
        route=scope['path'];method=scope['method']
        if route=='/plw-auth/login':
            if method=='GET':response=RedirectResponse('/',303) if session else self.login_page()
            elif method=='POST':
                if supplied_origin!=self.origin:response=Response('Forbidden',403)
                else:
                    try:fields=await self._fields(scope,receive)
                    except (ValueError,UnicodeError,TimeoutError):fields={}
                    if not self._valid_form(fields.get('csrf','')):response=self.login_page('登录页面已过期，请重试。',400)
                    else:
                        now=time.monotonic()
                        while self.attempts and self.attempts[0]<now-300:self.attempts.popleft()
                        if len(self.attempts)>=5 or self.checking:
                            response=self.login_page('尝试次数较多，请五分钟后再试。',429)
                            response.headers['Retry-After']='300'
                        else:
                            self.attempts.append(now);self.checking=True
                            try:correct=await asyncio.to_thread(verify_password,fields.get('password',''),self.digest)
                            finally:self.checking=False
                            correct=correct and hmac.compare_digest(fields.get('username','').encode(),self.username.encode())
                            if not correct:response=self.login_page('账号或密码不正确。',401)
                            else:
                                if len(self.sessions)>=128:
                                    self.sessions.pop(next(iter(self.sessions))).revoked.set()
                                if session:
                                    session.revoked.set();self.sessions.pop(connection.cookies.get(COOKIE,''),None)
                                key=secrets.token_urlsafe(32)
                                self.sessions[key]=Session(now+self.ttl,secrets.token_urlsafe(32),asyncio.Event())
                                response=RedirectResponse('/',303)
                                response.set_cookie(COOKIE,key,max_age=self.ttl,httponly=True,secure=self.secure,samesite='strict',path='/')
            else:response=Response(status_code=405)
            response.headers['Cache-Control']='no-store'
            return await response(scope,receive,send)
        if not session:
            response=RedirectResponse('/plw-auth/login',303) if method in ('GET','HEAD') and route=='/' else Response('请先登录 PLW。',401)
            response.headers['Cache-Control']='no-store'
            return await response(scope,receive,send)
        if route=='/plw-auth/logout':
            if method=='GET':response=self._page('<h1>退出登录</h1><p>退出后，此设备打开的学习页面会停止连接。</p><form method="post"><input type="hidden" name="csrf" value="'+session.csrf+'"><button>确认退出</button></form><p><a href="/">返回学习</a></p>')
            elif method=='POST' and supplied_origin==self.origin:
                try:fields=await self._fields(scope,receive)
                except (ValueError,UnicodeError,TimeoutError):fields={}
                if not hmac.compare_digest(fields.get('csrf','').encode(),session.csrf.encode()):response=Response('Forbidden',403)
                else:
                    session.revoked.set();self.sessions.pop(connection.cookies.get(COOKIE,''),None)
                    response=RedirectResponse('/plw-auth/login',303)
                    response.delete_cookie(COOKIE,path='/',secure=self.secure,httponly=True,samesite='strict')
            else:response=Response(status_code=403)
            response.headers['Cache-Control']='no-store'
            return await response(scope,receive,send)
        if method not in ('GET','HEAD','OPTIONS') and supplied_origin!=self.origin:
            return await Response('Forbidden',403)(scope,receive,send)
        async def protected_send(message):
            if message['type']=='http.response.start':
                cacheable=cacheable_asset_response(scope,message)
                headers=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'cache-control']
                if cacheable:
                    # Gzip and identity are different representations of the
                    # same framework file. Keep validators weak across both.
                    headers=[(k,b'W/'+v if k.lower()==b'etag' and not v.startswith(b'W/') else v) for k,v in headers]
                    if 'accept-encoding' not in {v.strip().lower() for v in Headers(raw=headers).get('vary','').split(',')}:
                        MutableHeaders(raw=headers).add_vary_header('Accept-Encoding')
                policy=b'private, max-age=86400, immutable' if cacheable else b'private, no-store'
                message={**message,'headers':headers+[(b'cache-control',policy),(b'x-frame-options',b'SAMEORIGIN')]}
            await send(message)
        if versioned_asset_request(scope) and accepts_gzip(scope):
            await self.compressed_assets(scope,receive,protected_send)
        else:
            await self.app(scope,receive,protected_send)
