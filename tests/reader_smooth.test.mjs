import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../src/plw/reader/reader.js',import.meta.url),'utf8');
const {createReaderSaveQueue,rememberPageRaster,releaseReaderDocument}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const model=()=>({run:'run',doc:'doc',page:1,revision:0,marks:[],pending:null});
const gate=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
const ack=action=>({ack:action.id,state:{revision:action.base_revision+1,marks:[]}});
const tick=()=>new Promise(r=>setTimeout(r,0));
test('latest unsent position is coalesced; one slow ACK never blocks another local page',async()=>{
 const m=model(),first=gate(),sent=[];
 const q=createReaderSaveQueue(m,{delayMs:10000,send:async a=>{sent.push(a);return sent.length===1?first.promise:ack(a);}});
 q.position(2);const p=q.flush();assert.equal(m.pending.page,2);
 m.page=3;q.position(3);m.page=5;q.position(5);assert.equal(m.page,5);assert.equal(sent.length,1);
 first.resolve(ack(sent[0]));await p;await tick();assert.deepEqual(sent.map(a=>a.page),[2,5]);assert.deepEqual(sent.map(a=>a.base_revision),[0,1]);assert.equal(m.pending,null);assert.equal(m.revision,2);assert.equal(m.page,5);
});
test('transport ambiguity retries the identical id/body, then sends the latest page',async()=>{
 const m=model(),sent=[];let fail=true;
 const q=createReaderSaveQueue(m,{delayMs:10000,send:async a=>{sent.push(structuredClone(a));if(fail)throw Error('lost ACK');return ack(a);}});
 q.position(2);await q.flush();assert.ok(m.saveError);const pending=m.pending;m.page=4;q.position(4);
 fail=false;q.retry();await tick();await tick();assert.deepEqual(sent[0],sent[1]);assert.equal(sent[2].page,4);assert.equal(sent[2].base_revision,1);assert.equal(m.page,4);assert.equal(m.pending,null);assert.equal(pending.page,2);
});
test('mark retains original page while navigation continues; no overlapping marks',async()=>{
 const m=model(),g=gate(),sent=[];m.page=3;
 const q=createReaderSaveQueue(m,{delayMs:10000,send:async a=>{sent.push(a);return sent.length===1?g.promise:ack(a);}});
 assert.equal(q.action({kind:'mark',type:'rectangle',points:[[0,0],[1,1]]}),true);
 assert.equal(q.action({kind:'undo'}),false);m.page=8;q.position(8);assert.equal(sent[0].page,3);
 g.resolve({...ack(sent[0]),state:{revision:1,marks:[{id:sent[0].id,page:3}]}});await tick();await tick();assert.deepEqual(sent.map(a=>a.kind),['mark','position']);assert.equal(m.page,8);
});
test('conflicts are retained for explicit retry, never silently rebased',async()=>{
 const m=model();let calls=0;const q=createReaderSaveQueue(m,{send:async()=>{calls++;throw Error('revision conflict');}});
 q.action({kind:'undo'});await tick();assert.equal(calls,1);assert.ok(m.pending);assert.equal(m.revision,0);assert.match(m.saveError,/conflict/);
});
test('raster cache has a strict pixel/count budget and is released with document',()=>{
 const m=model();for(let i=0;i<10;i++)rememberPageRaster(m,String(i),{bitmap:{width:100,height:100}},{bytes:100000,count:4});
 assert.deepEqual([...m.pageRasters.keys()],['8','9']);releaseReaderDocument(m);assert.equal(m.pageRasters.size,0);
 rememberPageRaster(m,'oversized',{bitmap:{width:10000,height:10000}});assert.equal(m.pageRasters.size,0);
});
