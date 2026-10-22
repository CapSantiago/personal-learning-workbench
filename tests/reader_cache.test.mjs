import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Import the production component module without invoking DOM/browser code.
const source=await readFile(new URL('../src/plw/reader/reader.js',import.meta.url),'utf8');
const {selectReaderModel:select,readerDocument:load,releaseReaderDocument:release}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const MB=1024*1024;
const data=(doc,extra={})=>({run:'dataset-a',base:'/reader/capability-a',doc,reset:'',digest:'sha-'+doc,bytes:28*MB,state:{page:1},...extra});
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};}
function task(pdf={}){return {promise:Promise.resolve(pdf),destroyed:0,destroy(){this.destroyed++;}};}

test('A -> B -> A reuses the PDF, thumbnails and reading position',async()=>{
  const registry=new Map(),a=select(registry,data('a'));a.page=15;a.thumbCache=new Map([[15,'bitmap']]);
  let loads=0;const first=task({name:'a'});
  const pdf=await load(a,()=>{loads++;return first;});
  const b=select(registry,data('b'));await load(b,()=>task({name:'b'}));
  const again=select(registry,data('a'));
  assert.equal(again,a);assert.equal(await load(again,()=>{loads++;throw Error('Must not reload');}),pdf);
  assert.equal(loads,1);assert.equal(first.destroyed,0);assert.equal(again.page,15);assert.equal(again.thumbCache.get(15),'bitmap');
});

test('three-document LRU evicts the least recently visited, not the current document',async()=>{
  const registry=new Map(),tasks={};
  for(const doc of ['a','b','c']){const m=select(registry,data(doc));tasks[doc]=task();await load(m,()=>tasks[doc]);}
  select(registry,data('a'));select(registry,data('d'));
  assert.deepEqual([...registry.keys()],['dataset-a:c','dataset-a:a','dataset-a:d']);assert.equal(tasks.b.destroyed,1);assert.equal(tasks.a.destroyed,0);
});

test('byte budget evicts older documents; an oversized active PDF stays usable',async()=>{
  const registry=new Map(),old=select(registry,data('a',{bytes:60*MB})),t=task();await load(old,()=>t);
  select(registry,data('b',{bytes:60*MB}));assert.equal(registry.has('dataset-a:a'),false);assert.equal(t.destroyed,1);
  const current=select(registry,data('huge',{bytes:120*MB}));assert.equal(registry.size,1);assert.equal(registry.get('dataset-a:huge'),current);
});

test('eviction releases PDF resources while preserving an unacknowledged action',async()=>{
  const registry=new Map(),a=select(registry,data('a',{bytes:60*MB})),t=task();a.pending={id:'unsaved-mark'};await load(a,()=>t);
  select(registry,data('b',{bytes:60*MB}));assert.equal(registry.get('dataset-a:a'),a);assert.equal(a.pending.id,'unsaved-mark');assert.equal(a.pdf,null);assert.equal(t.destroyed,1);
  assert.equal(select(registry,data('a',{bytes:60*MB})).pending.id,'unsaved-mark');
});

for(const [label,changed] of [['dataset',{run:'dataset-b'}],['capability',{base:'/reader/capability-b'}],['reload',{reset:'new'}],['content identity',{digest:'changed'}]]){
  test(label+' change invalidates the cached document',async()=>{
    const registry=new Map(),a=select(registry,data('a')),t=task();await load(a,()=>t);
    const next=select(registry,data('a',changed));assert.notEqual(next,a);assert.equal(t.destroyed,1);assert.equal(a.pdf,null);
  });
}

test('concurrent consumers share one loading task',async()=>{
  const m=select(new Map(),data('a')),gate=deferred(),t={promise:gate.promise,destroy(){}};let starts=0;
  const first=load(m,()=>{starts++;return t;}),second=load(m,()=>{starts++;return t;});
  gate.resolve('pdf');assert.deepEqual(await Promise.all([first,second]),['pdf','pdf']);assert.equal(starts,1);
});

test('a superseded load cannot overwrite a new PDF or clear its pending promise',async()=>{
  const m=select(new Map(),data('a')),oldGate=deferred(),newGate=deferred();
  const oldTask={promise:oldGate.promise,destroyed:0,destroy(){this.destroyed++;}};
  const old=load(m,()=>oldTask);await Promise.resolve();release(m);
  const newer=load(m,()=>({promise:newGate.promise,destroy(){}})),pending=m.loading;
  oldGate.resolve('old');await assert.rejects(old,/重新载入/);assert.equal(m.loading,pending);assert.equal(m.pdf,null);
  newGate.resolve('new');assert.equal(await newer,'new');assert.equal(m.pdf,'new');assert.equal(oldTask.destroyed,1);
});

test('a loading task created after invalidation is immediately released',async()=>{
  const m=select(new Map(),data('a')),factory=deferred(),t=task();
  const result=load(m,()=>factory.promise);release(m);factory.resolve(t);
  await assert.rejects(result,/重新载入/);assert.equal(t.destroyed,1);assert.equal(m.pdf,null);
});

test('failed loading tasks release their worker and permit a later retry',async()=>{
  const m=select(new Map(),data('a')),failed={promise:Promise.reject(Error('network')),destroyed:0,destroy(){this.destroyed++;}};
  await assert.rejects(load(m,()=>failed),/network/);assert.equal(failed.destroyed,1);assert.equal(m.loading,null);
  assert.equal(await load(m,()=>task('recovered')),'recovered');
});
