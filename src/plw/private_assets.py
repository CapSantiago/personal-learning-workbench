"""Delivery policy for versioned framework files, never learning data.

Only a hashed /static/{js,css,media} response that the framework itself marks
immutable may enter the private browser cache. Authentication stays outside
this policy. HTML, API responses, uploads, PDFs and backups remain no-store.
"""
import re

from starlette.datastructures import Headers


_VERSIONED = re.compile(
    r'/static/(?:js|css|media)/[A-Za-z0-9_.-]+[.-][A-Za-z0-9_-]{8}'
    r'\.(?:js|css|woff2?)'
)
_MIME = {
    '.js': {'application/javascript', 'text/javascript'},
    '.css': {'text/css'},
    '.woff': {'font/woff', 'application/font-woff'},
    '.woff2': {'font/woff2'},
}


def versioned_asset_request(scope):
    return (scope.get('type') == 'http'
            and scope.get('method') in ('GET', 'HEAD')
            and _VERSIONED.fullmatch(scope.get('path', '')) is not None)


def cacheable_asset_response(scope, message):
    if not versioned_asset_request(scope) or message.get('status') != 200:
        return False
    headers = Headers(raw=message.get('headers', []))
    cache = {part.strip().lower() for part in headers.get('cache-control', '').split(',')}
    suffix = '.' + scope['path'].rsplit('.', 1)[-1]
    mime = headers.get('content-type', '').split(';', 1)[0].strip().lower()
    return ('immutable' in cache and 'no-store' not in cache
            and 'set-cookie' not in headers
            and mime in _MIME.get(suffix, set()))


def accepts_gzip(scope):
    # Starlette's substring match alone also accepts gzip;q=0. Do not select
    # compression for such clients, HEAD or byte-range responses.
    headers = Headers(scope=scope)
    if scope.get('method') != 'GET' or 'range' in headers:
        return False
    for item in headers.get('accept-encoding', '').split(','):
        coding, *parameters = item.strip().split(';')
        if coding != 'gzip':
            continue
        quality = 1.0
        try:
            for parameter in parameters:
                key, separator, value = parameter.strip().partition('=')
                if key.lower() == 'q':
                    quality = float(value) if separator else 0.0
        except ValueError:
            return False
        return 0 < quality <= 1
    return False
