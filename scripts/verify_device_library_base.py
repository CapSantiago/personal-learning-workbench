"""Read-only base-image check, including the original Windows-newline UI.

Accepted UI digests are complete byte identities, not a permissive substring or
syntax check. The CRLF form is reconstructed from the immutable offline bundle
and its earlier cache-identity insertion, which preserved the source newlines.
"""
import hashlib
import json
from pathlib import Path
import sys

READERS={
    'plw:0.3.1-reader-compatfix-20261018':'7343d564dd2c43bb734a8e9616f951298dde85157e7a1889ec04e8da67c6ad60',
    'plw:0.3.1-reader-fullfilefix-20261018':'06f5290fa01ec54c6b93fee97687bdf96f472b02e6b82578da1963a97d727795',
}
UI={
    '13171adc616aeedd169d93c2eb7be6ed8d3093bf30140e440a626bd033ad64d5',
    '09dfa4a7c1af510285d3af2bd94f4c1b68eb873f817eff31ebdec7134b66fcd2',
}


def verify(base,tag):
    import streamlit
    assert streamlit.__version__=='1.65.0','Unexpected framework version'
    if tag not in READERS:raise ValueError('Unexpected base image tag')
    expected={
        'private_auth.py':{'0ff1ab929a353b99ea26b74854918ea8303181dec600651a73acccb80993065f'},
        'private_assets.py':{'dc809c6d46c501e282032ae26c192537b5e56c471cb94c8edce81edabdd002b6'},
        'reader_runtime.py':{'668baf4c3e1b3963f1b26c24ce600f991725532b66e4f20bd72321660388b2b4'},
        'reader/reader.js':{READERS[tag]},
        'ui_workbench.py':UI,
    }
    results={}
    for name,allowed in expected.items():
        data=(Path(base)/'src/plw'/name).read_bytes()
        actual=hashlib.sha256(data).hexdigest()
        if actual not in allowed:
            # Source digests/newline counts are sufficient; never print code,
            # server account files, capability URLs or learning data.
            raise ValueError(f'Unexpected previous file: {name}; sha256={actual}; '
                             f'CRLF={data.count(bytes([13,10]))}; LF={data.count(bytes([10]))}')
        results[name]=actual
    manifest=json.loads((Path(base)/'assets/pdfjs/manifest.json').read_text())
    digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert digest=='a99ceb0b2f1b4fd145df5b7cce03c2b3bb8198d5b76a5743851c07c1761d0aae','Unexpected vendor manifest baseline'
    return results


if __name__=='__main__':
    result=verify(Path('/app'),sys.argv[1])
    print('DEVICE LIBRARY BASE IMAGE CHECK PASSED; workbench UI SHA256 '+result['ui_workbench.py'])
