import asyncio
from http.cookies import SimpleCookie
import re
import time
from urllib.parse import urlencode

import pytest

from plw.private_auth import COOKIE,PrivateAccess,password_hash,verify_password

PASSWORD='Synthetic-login-only-2026'
ORIGIN='https://study.example.test'


async def inner(scope,receive,send):
    if scope['type']=='websocket':
        await receive();await send({'type':'websocket.accept'})
        while True:
            message=await receive()
            if message['type']=='websocket.disconnect':return
            await send({'type':'websocket.send','text':'saved'})
    else:
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'private content'})


@pytest.fixture(scope='module')
def digest():return password_hash(PASSWORD)


@pytest.fixture
def gate(digest):return PrivateAccess(inner,username='student',password_digest=digest,origin=ORIGIN)


async def fetch(gate,path='/',method='GET',*,cookie=None,origin=ORIGIN,form=None,extra=(),scheme='https'):
    headers=[(b'host',b'study.example.test'),*extra]
    if origin:headers.append((b'origin',origin.encode()))
    if cookie:headers.append((b'cookie',cookie.encode()))
    body=urlencode(form or {}).encode()
    if form is not None:headers.append((b'content-type',b'application/x-www-form-urlencoded'))
    scope=dict(type='http',asgi={'version':'3.0'},http_version='1.1',scheme=scheme,path=path,
        root_path='',query_string=b'',method=method,headers=headers,server=('study.example.test',443),client=('127.0.0.1',1234))
    sent=[]
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    async def send(message):sent.append(message)
    await gate(scope,receive,send)
    return sent[0]['status'],dict(sent[0].get('headers',[])),b''.join(m.get('body',b'') for m in sent)


async def login(gate,password=PASSWORD,username='student'):
    _,page_headers,body=await fetch(gate,'/plw-auth/login')
    assert page_headers[b'referrer-policy']==b'same-origin'
    csrf=re.search(rb'name="csrf" value="([^"]+)"',body)[1].decode()
    status,headers,body=await fetch(gate,'/plw-auth/login','POST',form={'username':username,'password':password,'csrf':csrf})
    cookie=headers.get(b'set-cookie',b'').decode().split(';')[0]
    return status,cookie,headers


def test_password_salted_hash_and_bounded_input(digest):
    assert password_hash(PASSWORD)!=digest
    assert verify_password(PASSWORD,digest)
    assert not verify_password('wrong',digest)
    assert not verify_password('x'*257,digest)
    with pytest.raises(ValueError):password_hash('short')


@pytest.mark.parametrize('path,method',[('/','GET'),('/_stcore/stream','GET'),('/_stcore/upload_file/a/b','PUT'),
    ('/plw-reader/copied/pdf/x.pdf','GET'),('/plw-reader/copied/download/x','GET'),('/media/backup.zip','GET'),('/static/app.js','GET')])
def test_all_private_http_routes_reject_anonymous(gate,path,method):
    status,_,body=asyncio.run(fetch(gate,path,method))
    assert status==(303 if path=='/' else 401)
    assert b'private content' not in body


def test_login_cookie_expiry_logout_and_copied_links(gate):
    async def scenario():
        status,cookie,headers=await login(gate)
        assert status==303
        value=headers[b'set-cookie'].decode()
        assert 'HttpOnly' in value and 'Secure' in value and 'SameSite=strict' in value
        assert (await fetch(gate,'/plw-reader/token/download/id',cookie=cookie))[0]==200
        assert (await fetch(gate,'/plw-reader/token/download/id'))[0]==401
        _,_,body=await fetch(gate,'/plw-auth/logout',cookie=cookie)
        csrf=re.search(rb'name="csrf" value="([^"]+)"',body)[1].decode()
        assert (await fetch(gate,'/plw-auth/logout','POST',cookie=cookie,form={'csrf':'恶意字段'}))[0]==403
        assert (await fetch(gate,'/plw-auth/logout','POST',cookie=cookie,form={'csrf':csrf}))[0]==303
        assert (await fetch(gate,'/plw-reader/token/download/id',cookie=cookie))[0]==401
        _,cookie,_=await login(gate)
        next(iter(gate.sessions.values())).expires=time.monotonic()-1
        assert (await fetch(gate,'/plw-reader/token/pdf/id.pdf',cookie=cookie))[0]==401
    asyncio.run(scenario())


def test_wrong_password_throttle_and_csrf(gate):
    async def scenario():
        assert (await fetch(gate,'/plw-auth/login','POST',form={'csrf':'fake'}))[0]==400
        for _ in range(5):assert (await login(gate,password='incorrect'))[0]==401
        assert (await login(gate))[0]==429
        assert not gate.sessions
    asyncio.run(scenario())


@pytest.mark.parametrize('origin,extra,scheme',[('https://evil.example',(),'https'),
    (None,((b'sec-fetch-site',b'cross-site'),),'https'),(ORIGIN,(),'http')])
def test_reject_cross_site_and_plain_http(gate,origin,extra,scheme):
    assert asyncio.run(fetch(gate,'/plw-auth/login',origin=origin,extra=extra,scheme=scheme))[0]==403


NAVIGATION=((b'sec-fetch-site',b'cross-site'),(b'sec-fetch-mode',b'navigate'),
            (b'sec-fetch-dest',b'document'))


@pytest.mark.parametrize('path,status',[('/',303),('/plw-auth/login',200)])
def test_external_entry_navigation_requires_login(gate,path,status):
    result,headers,body=asyncio.run(fetch(gate,path,origin=None,extra=NAVIGATION))
    assert result==status
    assert b'private content' not in body
    assert not gate.sessions
    if path=='/':assert headers[b'location']==b'/plw-auth/login'


@pytest.mark.parametrize('path,method,origin,extra',[
    ('/','HEAD',None,NAVIGATION),
    ('/plw-auth/login','HEAD',None,NAVIGATION),
    ('/','POST',None,NAVIGATION),
    ('/plw-auth/login','POST',ORIGIN,NAVIGATION),
    ('/plw-auth/login','GET','https://evil.example',NAVIGATION),
    ('/plw-reader/token/download/id','GET',None,NAVIGATION),
    ('/_stcore/upload_file/a/b','PUT',None,NAVIGATION),
    ('/plw-auth/logout','GET',None,NAVIGATION),
    ('/','GET',None,((b'sec-fetch-site',b'cross-site'),(b'sec-fetch-mode',b'cors'),(b'sec-fetch-dest',b'document'))),
    ('/','GET',None,((b'sec-fetch-site',b'cross-site'),(b'sec-fetch-mode',b'navigate'),(b'sec-fetch-dest',b'iframe'))),
])
def test_external_navigation_does_not_open_private_routes(gate,path,method,origin,extra):
    async def scenario():
        _,cookie,_=await login(gate)
        status,_,body=await fetch(gate,path,method,cookie=cookie,origin=origin,extra=extra)
        assert status==403
        assert b'private content' not in body
    asyncio.run(scenario())


@pytest.mark.parametrize('host,scheme',[(b'evil.example','https'),(b'study.example.test','http')])
def test_external_entry_keeps_host_and_https_checks(digest,host,scheme):
    app=PrivateAccess(inner,username='student',password_digest=digest,origin=ORIGIN)
    # A separate Host header is used to avoid duplicate-header semantics.
    async def scenario():
        sent=[]
        scope=dict(type='http',method='GET',path='/',scheme=scheme,
                   headers=[(b'host',host),*NAVIGATION],query_string=b'')
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):sent.append(message)
        await app(scope,receive,send)
        return sent[0]['status']
    assert asyncio.run(scenario())==403


def test_websocket_auth_origin_logout_and_expiry(gate):
    async def scenario():
        incoming=asyncio.Queue();sent=asyncio.Queue()
        def scope(cookie=None,origin=ORIGIN):
            return dict(type='websocket',scheme='wss',path='/_stcore/stream',headers=[(b'host',b'study.example.test'),(b'origin',origin.encode()),(b'cookie',(cookie or '').encode())],query_string=b'')
        await gate(scope(),incoming.get,sent.put)
        assert (await sent.get())['code']==1008
        _,cookie,_=await login(gate)
        await gate(scope(cookie,'https://evil.example'),incoming.get,sent.put)
        assert (await sent.get())['code']==1008
        running=asyncio.create_task(gate(scope(cookie),incoming.get,sent.put))
        await incoming.put({'type':'websocket.connect'})
        assert (await sent.get())['type']=='websocket.accept'
        session=next(iter(gate.sessions.values()))
        await fetch(gate,'/plw-auth/logout','POST',cookie=cookie,form={'csrf':session.csrf})
        assert (await asyncio.wait_for(sent.get(),2))=={'type':'websocket.close','code':4001}
        await running
        _,cookie,_=await login(gate)
        session=next(iter(gate.sessions.values()));session.expires=time.monotonic()+.1
        running=asyncio.create_task(gate(scope(cookie),incoming.get,sent.put))
        await incoming.put({'type':'websocket.connect'});await sent.get()
        assert (await asyncio.wait_for(sent.get(),2))['code']==4001
        await running
    asyncio.run(scenario())
