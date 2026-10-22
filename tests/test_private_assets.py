"""Real framework static-handler integration with a synthetic private session."""
import asyncio
import gzip
import time

import pytest
from starlette.responses import Response
from streamlit.web.server.starlette.starlette_static_routes import create_streamlit_static_handler

from plw.private_auth import COOKIE, PrivateAccess, Session


ORIGIN = 'https://study.example.test'
ASSET = '/static/js/test.Abc12345.js'
BODY = b'const synthetic = "private framework delivery test";\n' * 10000


def gate_for(app):
    gate = PrivateAccess(app, username='synthetic', origin=ORIGIN,
                         password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic'] = Session(time.monotonic()+600, 'csrf', asyncio.Event())
    return gate


async def request(gate, path=ASSET, *, authenticated=True, method='GET', extra=()):
    headers = [(b'host', b'study.example.test'), *extra]
    if authenticated:
        headers.append((b'cookie', f'{COOKIE}=synthetic'.encode()))
    scope = dict(type='http', asgi={'version': '3.0', 'spec_version': '2.4'},
                 http_version='2', scheme='https', method=method, path=path,
                 root_path='', query_string=b'', headers=headers,
                 server=('study.example.test',443), client=('127.0.0.1',1234))
    sent = []
    async def receive():
        return {'type':'http.request', 'body':b'', 'more_body':False}
    async def send(message):
        sent.append({**message, 'headers':list(message.get('headers',[]))})
    await gate(scope, receive, send)
    start = sent[0]
    return start['status'], dict(start['headers']), b''.join(m.get('body',b'') for m in sent)


@pytest.fixture
def static_gate(tmp_path):
    asset = tmp_path / ASSET.lstrip('/')
    asset.parent.mkdir(parents=True)
    asset.write_bytes(BODY)
    (tmp_path/'index.html').write_text('<html>synthetic entry</html>')
    return gate_for(create_streamlit_static_handler(str(tmp_path), None))


def test_large_real_framework_asset_streams_gzip_and_caches_privately(static_gate):
    status, headers, body = asyncio.run(request(static_gate, extra=((b'accept-encoding',b'gzip, br'),)))
    assert status == 200
    assert headers[b'content-encoding'] == b'gzip'
    assert gzip.decompress(body) == BODY
    assert len(body) < len(BODY)/4
    assert headers[b'cache-control'] == b'private, max-age=86400, immutable'
    assert headers[b'etag'].startswith(b'W/')
    assert b'content-length' not in headers  # FileResponse streams in chunks.
    assert b'set-cookie' not in headers


@pytest.mark.parametrize('extra', [(), ((b'accept-encoding',b'gzip;q=0, br'),)])
def test_identity_and_disabled_gzip_remain_valid(static_gate, extra):
    status, headers, body = asyncio.run(request(static_gate, extra=extra))
    assert status == 200 and body == BODY
    assert b'content-encoding' not in headers
    assert headers[b'cache-control'].startswith(b'private, max-age=')
    assert headers[b'vary'] == b'Accept-Encoding'


def test_head_range_and_conditional_requests_remain_valid(static_gate):
    async def scenario():
        status, headers, body = await request(static_gate, method='HEAD', extra=((b'accept-encoding',b'gzip'),))
        assert status == 200 and body == b'' and b'content-encoding' not in headers
        assert int(headers[b'content-length']) == len(BODY)
        etag = headers[b'etag']
        assert (await request(static_gate, extra=((b'if-none-match',etag),)))[0] == 304
        status, headers, body = await request(static_gate, extra=((b'accept-encoding',b'gzip'),(b'range',b'bytes=0-9')))
        assert status == 206 and body == BODY[:10]
        assert b'content-encoding' not in headers
        assert headers[b'cache-control'] == b'private, no-store'
    asyncio.run(scenario())


def test_static_still_requires_authentication_and_same_site(static_gate):
    async def scenario():
        for extra in ((), ((b'if-none-match',b'"pretend"'),)):
            status, headers, body = await request(static_gate, authenticated=False, extra=extra)
            assert status == 401 and BODY not in body
            assert headers[b'cache-control'] == b'no-store'
        assert (await request(static_gate, extra=((b'sec-fetch-site',b'cross-site'),)))[0] == 403
        static_gate.sessions.clear()
        assert (await request(static_gate))[0] == 401
    asyncio.run(scenario())


@pytest.mark.parametrize('path', ['/', '/static/js/missing.Abc12345.js',
    '/static/js/unversioned.js', '/plw-reader/copied/pdf/file.pdf', '/media/backup.zip'])
def test_html_fallback_and_private_routes_never_enter_asset_cache(static_gate, path):
    status, headers, _ = asyncio.run(request(static_gate, path))
    assert status == 200  # Framework SPA fallback; policy must check MIME/header too.
    assert headers[b'cache-control'] == b'private, no-store'


@pytest.mark.parametrize('status,kind,cookie,cache', [
    (404,'application/javascript',False,'public, immutable'),
    (200,'text/html',False,'public, immutable'),
    (200,'application/javascript',True,'public, immutable'),
    (200,'application/javascript',False,'private, no-store'),
])
def test_errors_dynamic_content_and_cookie_responses_are_not_cacheable(status,kind,cookie,cache):
    async def app(scope,receive,send):
        headers = {'Cache-Control':cache}
        if cookie: headers['Set-Cookie']='synthetic=value'
        await Response(b'synthetic',status_code=status,media_type=kind,headers=headers)(scope,receive,send)
    _, headers, _ = asyncio.run(request(gate_for(app)))
    assert headers[b'cache-control'] == b'private, no-store'


def test_asset_cache_keeps_existing_vary_fields():
    async def app(scope,receive,send):
        await Response(b'synthetic',media_type='application/javascript',headers={
            'Cache-Control':'public, immutable', 'Vary':'Origin'})(scope,receive,send)
    _, headers, _ = asyncio.run(request(gate_for(app)))
    assert {v.strip().lower() for v in headers[b'vary'].split(b',')} == {b'origin',b'accept-encoding'}
