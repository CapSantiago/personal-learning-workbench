"""Accept only exact, already-delivered PLW versions before replacing UI files."""
from pathlib import Path
import hashlib,json,sys
VARIANTS = {'plw:0.3.1-device-library-20261021-r2': {'ui_workbench.py': ['3697ee42c08fd3854bf0cb06a59dc0ba169bab2f615f9c6f803694b5446dca58', '5a7b8b4d9f850019fad1af636e6d0fdc2d1dbd1c05fe6b220eed986d11a6b7c1'], 'workbench.css': ['cdb907a42264a888b041991db201f29060c4a4e6796c45ae13fb8d24cbb205e3'], 'reader/reader.css': ['7e873ac0c6a8089e81283354df170b348b363390eee9c5a919e8126205117f74', 'ad6b752b865ad472be5258e09924651c550fcc4066680f44d77bf76e07c9d6a9'], 'reader/reader.js': ['4459c763e0a9e3ea10802d62ec3b17b71ee411ef9d1cdf315172f660c0822007'], 'reader_runtime.py': ['ccd5298a989e5bf8f618ac4dc7d03b8f186cbc2bf863066e64f26b3b679b4104'], 'reader/library.css': ['1cdae34be2700c91a5092b1a946b565927eb429d6afa1d5115d1730d85fde61d']}, 'plw:0.3.1-reader-smooth-20261022': {'ui_workbench.py': ['3697ee42c08fd3854bf0cb06a59dc0ba169bab2f615f9c6f803694b5446dca58', '5a7b8b4d9f850019fad1af636e6d0fdc2d1dbd1c05fe6b220eed986d11a6b7c1'], 'workbench.css': ['cdb907a42264a888b041991db201f29060c4a4e6796c45ae13fb8d24cbb205e3'], 'reader/reader.css': ['7e873ac0c6a8089e81283354df170b348b363390eee9c5a919e8126205117f74', 'ad6b752b865ad472be5258e09924651c550fcc4066680f44d77bf76e07c9d6a9'], 'reader/reader.js': ['99e3d236b30b7d3618cb6dfbea265fa61c0ef98df249dfe368970017a0fb7236'], 'reader_runtime.py': ['fa26a744e4d09068586228c7ac2fe3bd3b90400a729c77ba6a364af4f3cb2855'], 'reader/library.css': ['1cdae34be2700c91a5092b1a946b565927eb429d6afa1d5115d1730d85fde61d']}, 'plw:0.3.1-reading-workspace-20261022': {'ui_workbench.py': ['dd91f129bcea6cc894fd60cbd64fd69a921c427dea50c7540c1ae27f11475c89'], 'workbench.css': ['176b96d68428737986f73463488abf0a2eada2abad29912506b983cf79bbb41c'], 'reader/reader.css': ['ba205f06f570c24859070d1af5f21c8f71aa0dd7fcb5ea98dc9a7f0d36c0bd08'], 'reader/reader.js': ['6030ea73a4bf8698401d734dc98ceeda8b5c92f72a67b09558852d234774dfe2'], 'reader_runtime.py': ['fa26a744e4d09068586228c7ac2fe3bd3b90400a729c77ba6a364af4f3cb2855'], 'reader/library.css': ['1cdae34be2700c91a5092b1a946b565927eb429d6afa1d5115d1730d85fde61d']}}
COMMON = {'reader/device_library.js': ['17639c13cc378e5b69a4d41a8b936af0b40e33c2d3cfc130ae805e05864c8c44'], 'reader/library_ui.js': ['c98973f985944bf3e13bae171e0e89515ae8b092c8d59164f7ffe957992db880'], 'private_auth.py': ['0ff1ab929a353b99ea26b74854918ea8303181dec600651a73acccb80993065f'], 'private_assets.py': ['dc809c6d46c501e282032ae26c192537b5e56c471cb94c8edce81edabdd002b6']}
def verify(base,tag):
 import streamlit
 if streamlit.__version__!='1.65.0':raise ValueError('Unexpected framework version')
 if tag not in VARIANTS:raise ValueError('Unexpected image tag')
 base=Path(base)
 if (base/'src/plw/design_tokens.css').exists():raise ValueError('Unexpected existing design tokens')
 for name,allowed in {**COMMON,**VARIANTS[tag]}.items():
  path=base/'src/plw'/name
  if path.is_symlink() or not path.is_file():raise ValueError('Unexpected baseline file: '+name)
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  if digest not in allowed:raise ValueError('Unexpected baseline: '+name+'; SHA256='+digest)
 manifest=json.loads((base/'assets/pdfjs/manifest.json').read_text())
 if hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()!='a99ceb0b2f1b4fd145df5b7cce03c2b3bb8198d5b76a5743851c07c1761d0aae':raise ValueError('Unexpected PDF runtime manifest')
 print('UI DESIGN BASE CHECK PASSED: '+tag)
if __name__=='__main__':verify(Path('/app'),sys.argv[1])
