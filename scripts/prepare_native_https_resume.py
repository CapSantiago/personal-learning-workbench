"""Reuse only the exact, untouched first package after its preflight failure."""
import hashlib
import json
import os
from pathlib import Path

PREVIOUS={
    'caddy':'678ade3bfc088749c81a681adc603333ee0bb023b6a6cfe3c0f58bef8ff854e9',
    'CADDY-LICENSE':'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'install_native_https.py':'ca5443bb113e6dd8a38fd77b942ddbf1bd368b3769db3dbb2e1faa79baf711ce',
    'native_https_config.py':'3a51a26eeb03325d78561ad7d86bd032e047f3e322261bdb68d6351d93fb985d',
    'README.md':'15ada3a44764bb163c094aa112ab2609883e2f41ac5445b2de248e0f13e7ad2f',
    'rollback_native_https.py':'b0ac4e859e91fa2535666022d2928a26282cf2018e5388c40fe5d1dd24940017',
}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def prepare(previous,target,payload):
    previous=Path(previous);target=Path(target)
    if previous.is_symlink() or not previous.is_dir():raise RuntimeError('Expected previous package folder missing or linked')
    if target.exists() or target.is_symlink():raise RuntimeError('Resume folder already exists; inspect before retrying')
    allowed=set(PREVIOUS)|{'manifest.json','__pycache__'}
    if set(p.name for p in previous.iterdir())-allowed:
        raise RuntimeError('Previous attempt progressed past initial preflight; inspect it before resuming')
    cache=previous/'__pycache__'
    if cache.is_symlink() or cache.exists() and not cache.is_dir():raise RuntimeError('Unexpected previous bytecode path')
    for name,expected in PREVIOUS.items():
        source=previous/name
        if source.is_symlink() or not source.is_file() or digest(source)!=expected:
            raise RuntimeError('Previous payload changed: '+name)
    manifest=previous/'manifest.json'
    if manifest.is_symlink() or not manifest.is_file():raise RuntimeError('Invalid previous manifest')
    records=json.loads(manifest.read_text(encoding='utf-8'))
    if {name:records.get(name) for name in PREVIOUS}!=PREVIOUS:raise RuntimeError('Previous manifest differs')
    if not payload or any(Path(name).name!=name or name in ('caddy','CADDY-LICENSE') for name in payload):
        raise RuntimeError('Invalid resume payload names')
    target.mkdir(mode=0o700)
    # Never import or execute old __pycache__. Copy into a clean new directory.
    for name in ('caddy','CADDY-LICENSE'):
        descriptor=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o700 if name=='caddy' else 0o600)
        with (previous/name).open('rb') as source,os.fdopen(descriptor,'wb') as output:
            while chunk:=source.read(1024*1024):output.write(chunk)
        if digest(target/name)!=PREVIOUS[name]:raise RuntimeError('Copied payload differs: '+name)
    for name,data in payload.items():
        descriptor=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as output:output.write(data)
    return {'reused_binary_sha256':PREVIOUS['caddy'],'previous_folder_preserved':True,
            'copied_to':str(target)}
