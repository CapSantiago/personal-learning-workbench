"""Offline smoke check against the installed Streamlit assets; no real account."""
import asyncio
import gzip
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, '/app/src')
from streamlit import file_util
from streamlit.web.server.starlette.starlette_static_routes import create_streamlit_static_handler
from plw.private_auth import COOKIE, PrivateAccess, Session


def entry_asset_path(directory):
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sources = []

        def handle_starttag(self,tag,attrs):
            values = dict(attrs)
            source = values.get('src','')
            if tag == 'script' and values.get('type') == 'module' and re.fullmatch(
                    r'\./static/js/index\.[A-Za-z0-9_-]{8}\.js',source):
                self.sources.append('/'+source.removeprefix('./'))

    parser = Scripts()
    parser.feed((directory/'index.html').read_text(encoding='utf-8'))
    assert len(parser.sources) == 1, 'Expected one framework module entry in index.html'
    return parser.sources[0]


async def main():
    directory = Path(file_util.get_static_dir())
    path = entry_asset_path(directory)
    original = (directory/path.lstrip('/')).read_bytes()
    app = create_streamlit_static_handler(str(directory), None)
    gate = PrivateAccess(app, username='synthetic', origin='https://study.example.test',
                         password_digest='scrypt$'+'00'*16+'$'+'00'*64)
    gate.sessions['synthetic'] = Session(time.monotonic()+600, 'csrf', asyncio.Event())

    async def request(asset, *, auth=True, encoding=b'gzip', origin=None, extra=()):
        headers = [(b'host',b'study.example.test'),(b'accept-encoding',encoding),*extra]
        if auth: headers.append((b'cookie',f'{COOKIE}=synthetic'.encode()))
        if origin: headers.append((b'origin',origin))
        scope = dict(type='http', asgi={'version':'3.0','spec_version':'2.4'}, http_version='2',
                     method='GET', path=asset, root_path='', query_string=b'', scheme='https',
                     headers=headers, server=('study.example.test',443), client=('127.0.0.1',1234))
        sent = []
        async def receive(): return {'type':'http.request','body':b'','more_body':False}
        async def send(message): sent.append({**message,'headers':list(message.get('headers',[]))})
        await gate(scope,receive,send)
        return sent[0]['status'],dict(sent[0]['headers']),b''.join(m.get('body',b'') for m in sent)

    status, headers, body = await request(path)
    assert status == 200 and headers[b'content-encoding'] == b'gzip'
    assert gzip.decompress(body) == original and len(body) < len(original)*0.6
    assert headers[b'cache-control'] == b'private, max-age=86400, immutable'
    assert headers[b'etag'].startswith(b'W/')
    compressed_size = len(body)
    assert (await request(path,auth=False))[0] == 401
    assert (await request(path,origin=b'https://evil.example'))[0] == 403
    assert (await request(path,extra=((b'sec-fetch-site',b'cross-site'),)))[0] == 403
    status, headers, body = await request(path,encoding=b'gzip;q=0, br')
    assert status == 200 and body == original and b'content-encoding' not in headers
    for asset in ('/','/static/js/missing.Abc12345.js','/plw-reader/file.pdf','/media/backup.zip'):
        status, headers, _ = await request(asset)
        assert headers[b'cache-control'] == b'private, no-store'
    gate.sessions.clear()
    assert (await request(path))[0] == 401
    print(f'STATIC ASSETS SYNTHETIC CHECK PASSED: index {len(original)} -> {compressed_size} bytes')


if __name__ == '__main__':
    asyncio.run(main())
