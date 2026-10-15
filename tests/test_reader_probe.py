"""R0 contract tests, synthetic experiment directories only."""
import copy
import importlib.util
import math
from pathlib import Path
import uuid
import pytest

spec=importlib.util.spec_from_file_location('plw_r0_core',Path(__file__).parents[1]/'scripts/reader_probe/probe_core.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

@pytest.fixture
def setup():
    root=core.BASE/str(uuid.uuid4());root.mkdir(parents=True)
    store=core.ProbeStore(root)
    docs={'a'*64:{'sha256':'a'*64,'pages':3}}
    action={'id':str(uuid.uuid4()),'run':root.name,'doc':'a'*64,'base_revision':0,'kind':'mark','page':1,'type':'ink','points':[[.1,.2],[.3,.4]]}
    return store,docs,action

def test_persistence_and_replay(setup):
    store,docs,a=setup
    store.apply(a,docs);store.apply(a,docs)
    recovered=core.ProbeStore(store.root).read()
    assert recovered['revision']==1
    assert len(recovered['documents'][a['doc']]['marks'])==1

def test_failed_save_retains_previous_and_retries(setup):
    store,docs,a=setup
    with pytest.raises(OSError):store.apply(a,docs,fail=True)
    assert store.read()['revision']==0
    store.apply(a,docs);assert store.read()['revision']==1

@pytest.mark.parametrize('field,value',[('run',str(uuid.uuid4())),('doc','b'*64),('base_revision',2),('page',0),('page',4),('page',True),('type','script'),('points',[[float('nan'),.2],[.3,.4]]),('points',[[-.1,.2],[.3,.4]]),('points',[[.1,.2]]),('points',[[.1,.2]]*4097)])
def test_reject_invalid_operation(setup,field,value):
    store,docs,a=setup;a[field]=value
    with pytest.raises((ValueError,TypeError)):store.apply(a,docs)
    assert store.read()['revision']==0

def test_reused_id_changed_payload(setup):
    store,docs,a=setup;store.apply(a,docs);a['page']=2
    with pytest.raises(ValueError,match='reused'):store.apply(a,docs)

def test_concurrent_revision_and_source_editions(setup):
    store,docs,a=setup;store.apply(a,docs)
    stale=copy.deepcopy(a);stale['id']=str(uuid.uuid4())
    with pytest.raises(ValueError,match='Revision'):store.apply(stale,docs)
    docs['b'*64]={'sha256':'b'*64,'pages':3};stale.update(doc='b'*64,base_revision=1)
    store.apply(stale,docs)
    assert len(store.document('a'*64)['marks'])==len(store.document('b'*64)['marks'])==1

def test_path_escape():
    with pytest.raises(ValueError):core.confined(Path(r'E:\outside.pdf'),core.BASE)
    with pytest.raises(ValueError):core.confined(core.BASE/'../outside.pdf',core.BASE)
    with pytest.raises(ValueError):core.run_root('../m2')
