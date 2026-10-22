"""Only patch the known deployed UI; do not replace unrelated workbench code."""
from pathlib import Path
import hashlib,sys
BEFORE_DIGEST='13171adc616aeedd169d93c2eb7be6ed8d3093bf30140e440a626bd033ad64d5'
AFTER_DIGEST='5a7b8b4d9f850019fad1af636e6d0fdc2d1dbd1c05fe6b220eed986d11a6b7c1'
INSERT=b'def device_downloads(path):\n    assets=reader_assets(f"http://127.0.0.1:{st.get_option(\'server.port\')}")\n    url=assets.register_library(path);folder=Path(__file__).with_name(\'reader\')\n    with st.expander(\'\xe6\xad\xa4\xe8\xae\xbe\xe5\xa4\x87\xe8\xaf\xbe\xe4\xbb\xb6\xe4\xb8\x8b\xe8\xbd\xbd\xe5\xba\x93\'):\n        render=st.components.v2.component(\'plw_device_library\',html=\'<div class="device-library"></div>\',\n            css=(folder/\'library.css\').read_text(encoding=\'utf-8\'),js=(folder/\'library_ui.js\').read_text(encoding=\'utf-8\'))\n        render(key=\'device_library_\'+path.parent.name,data={\'base\':assets.url,\'run\':path.parent.name,\'manifest\':url})\n\n\n'
def patch(path):
    path=Path(path);original=path.read_bytes();normalized=original.replace(b'\r\n',b'\n')
    if hashlib.sha256(normalized).hexdigest()!=BEFORE_DIGEST:raise ValueError('Unexpected workbench UI baseline')
    pairs=[(b'def read_edition(path,edition):',INSERT+b'def read_edition(path,edition):'),
      (b"'doc':identity,'pages':",b"'doc':identity,'filename':material['name'],'pages':"),
      (b'def bookshelf(path):\n',b'def bookshelf(path):\n    device_downloads(path)\n')]
    for before,after in pairs:
        if normalized.count(before)!=1:raise ValueError('Unexpected UI insertion anchor')
        normalized=normalized.replace(before,after,1)
    if hashlib.sha256(normalized).hexdigest()!=AFTER_DIGEST:raise ValueError('Patched UI differs from verified source')
    newline=b'\r\n' if b'\r\n' in original else b'\n'
    path.write_bytes(normalized.replace(b'\n',newline))
if __name__=='__main__':patch(sys.argv[1] if len(sys.argv)>1 else '/app/src/plw/ui_workbench.py')
