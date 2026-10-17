"""Synthetic ASGI checks; no account, network, or production volumes required."""
import asyncio
import sys

sys.path.insert(0, '/app/src')
from plw.private_auth import PrivateAccess


async def inner(scope, receive, send):
    raise AssertionError('Anonymous request reached the private application')


async def request(gate, path='/', method='GET', *, mode='navigate', dest='document',
                  host='study.example.test', origin=None, kind='http'):
    headers = [(b'host', host.encode()), (b'sec-fetch-site', b'cross-site'),
               (b'sec-fetch-mode', mode.encode()), (b'sec-fetch-dest', dest.encode())]
    if origin is not None:
        headers.append((b'origin', origin.encode()))
    scope = dict(type=kind, asgi={'version': '3.0'}, http_version='1.1',
                 scheme='wss' if kind == 'websocket' else 'https', path=path,
                 root_path='', query_string=b'', method=method, headers=headers,
                 server=('study.example.test', 443), client=('127.0.0.1', 1234))
    sent = []
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        sent.append(message)
    await gate(scope, receive, send)
    return sent


async def main():
    # Well-formed synthetic digest; no password verification or real config is read.
    gate = PrivateAccess(inner, username='synthetic',
                         password_digest='scrypt$' + '00' * 16 + '$' + '00' * 64,
                         origin='https://study.example.test')
    assert (await request(gate))[0]['status'] == 303
    page = await request(gate, '/plw-auth/login')
    assert page[0]['status'] == 200
    assert b'<form' in b''.join(m.get('body', b'') for m in page)
    for path in ('/static/app.js', '/media/backup.zip', '/plw-auth/logout'):
        assert (await request(gate, path))[0]['status'] == 403
    for kwargs in ({'method': 'POST'}, {'method': 'HEAD'}, {'dest': 'iframe'},
                   {'mode': 'cors'}, {'host': 'evil.example'},
                   {'origin': 'https://evil.example'}):
        assert (await request(gate, '/plw-auth/login', **kwargs))[0]['status'] == 403
    ws = await request(gate, '/_stcore/stream', kind='websocket')
    assert ws[0] == {'type': 'websocket.close', 'code': 1008}
    print('ENTRY HOTFIX SYNTHETIC CHECK PASSED')


if __name__ == '__main__':
    asyncio.run(main())
