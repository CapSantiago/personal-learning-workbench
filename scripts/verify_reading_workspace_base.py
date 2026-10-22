"""Strict identities for the two already-delivered reader versions."""
from pathlib import Path
import hashlib,json,sys

READERS={
 'plw:0.3.1-device-library-20261021-r2':('4459c763e0a9e3ea10802d62ec3b17b71ee411ef9d1cdf315172f660c0822007','ccd5298a989e5bf8f618ac4dc7d03b8f186cbc2bf863066e64f26b3b679b4104'),
 'plw:0.3.1-reader-smooth-20261022':('99e3d236b30b7d3618cb6dfbea265fa61c0ef98df249dfe368970017a0fb7236','fa26a744e4d09068586228c7ac2fe3bd3b90400a729c77ba6a364af4f3cb2855'),
}
def verify(base,tag):
 import streamlit
 assert streamlit.__version__=='1.65.0','Unexpected framework version'
 if tag not in READERS:raise ValueError('Unexpected image tag')
 expected={
 'reader/reader.js':{READERS[tag][0]},'reader_runtime.py':{READERS[tag][1]},
 'ui_workbench.py':{'5a7b8b4d9f850019fad1af636e6d0fdc2d1dbd1c05fe6b220eed986d11a6b7c1','3697ee42c08fd3854bf0cb06a59dc0ba169bab2f615f9c6f803694b5446dca58'},
 'reader/reader.css':{'7e873ac0c6a8089e81283354df170b348b363390eee9c5a919e8126205117f74','ad6b752b865ad472be5258e09924651c550fcc4066680f44d77bf76e07c9d6a9'},
 'workbench.css':{'cdb907a42264a888b041991db201f29060c4a4e6796c45ae13fb8d24cbb205e3'},
 'reader/device_library.js':{'17639c13cc378e5b69a4d41a8b936af0b40e33c2d3cfc130ae805e05864c8c44'},
 'private_auth.py':{'0ff1ab929a353b99ea26b74854918ea8303181dec600651a73acccb80993065f'},
 'private_assets.py':{'dc809c6d46c501e282032ae26c192537b5e56c471cb94c8edce81edabdd002b6'}}
 for name,allowed in expected.items():
  digest=hashlib.sha256((Path(base)/'src/plw'/name).read_bytes()).hexdigest()
  if digest not in allowed:raise ValueError('Unexpected baseline: '+name+'; SHA256='+digest)
 manifest=json.loads((Path(base)/'assets/pdfjs/manifest.json').read_text())
 assert hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()=='a99ceb0b2f1b4fd145df5b7cce03c2b3bb8198d5b76a5743851c07c1761d0aae'
 print('READING WORKSPACE BASE CHECK PASSED')
if __name__=='__main__':verify(Path('/app'),sys.argv[1])
