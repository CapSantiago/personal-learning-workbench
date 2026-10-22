import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
const require=createRequire(new URL('../.sandbox/device-library-test-runtime/package.json',import.meta.url));
const {IDBFactory}=require('fake-indexeddb');
const source=await readFile(new URL('../src/plw/reader/device_library.js',import.meta.url),'utf8');
const lib=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const factory=new IDBFactory(),body=new TextEncoder().encode('%PDF-1.7 real device download test');
const digest=await lib.fileDigest(body);
const item=(id='a',extra={})=>({id,kind:'pdf',bytes:body.length,digest,mime:'application/pdf',filename:id+'.pdf',url:'https://private.example/capability-secret/download/'+id,...extra});
const open=(name=crypto.randomUUID())=>lib.openDeviceLibrary({factory,name});

test('download once survives a database close/reopen and a new application model',async()=>{
  const store=await open(),name=store.name;let calls=0;
  const first=await lib.ensureDeviceFile({store,run:'dataset',item:item(),download:async()=>{calls++;return body;}});
  assert.equal(first.local,false);store.close();
  const reopened=await open(name);
  const second=await lib.ensureDeviceFile({store:reopened,run:'dataset',item:item(),download:()=>assert.fail('Must read the saved file')});
  assert.equal(second.local,true);assert.deepEqual(second.bytes,body);assert.equal(calls,1);reopened.close();
});

test('PDF reading copy and original with identical bytes share the stored file',async()=>{
  const store=await open();let calls=0;
  const download=async()=>{calls++;return body;};
  await lib.ensureDeviceFile({store,run:'dataset',item:item(),download});
  await lib.ensureDeviceFile({store,run:'dataset',item:item('original',{kind:'original'}),download});
  assert.equal(calls,1);assert.equal((await store.items('dataset')).length,2);store.close();
});

test('changed versions download once; unchanged files are reused on the next update',async()=>{
  const store=await open();let calls=0;const newer=new Uint8Array([...body,32]),newDigest=await lib.fileDigest(newer);
  const download=async(url,meta)=>{calls++;return meta.digest===digest?body:newer;};
  await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files:[item('a'),item('b')]},download});
  assert.equal(calls,1); // Same content, two identities.
  const result=await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files:[item('a'),item('b',{bytes:newer.length,digest:newDigest})]},download});
  assert.equal(calls,2);assert.equal(result.reused,1);assert.equal(result.downloaded,1);
  const again=await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files:[item('a'),item('b',{bytes:newer.length,digest:newDigest})]},download});
  assert.equal(again.reused,2);assert.equal(calls,2);store.close();
});

test('interrupted bulk update retains completed files and only retries missing files',async()=>{
  const store=await open(),other=new Uint8Array([...body,40]),otherDigest=await lib.fileDigest(other);
  const files=[item('a'),item('b',{bytes:other.length,digest:otherDigest})];
  const first=await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files},download:async(url)=>{if(url.endsWith('/b'))throw Error('Network stopped');return body;}});
  assert.equal(first.downloaded,1);assert.equal(first.failed.length,1);
  let calls=0;
  const next=await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files},download:async()=>{calls++;return other;}});
  assert.equal(next.reused,1);assert.equal(next.downloaded,1);assert.equal(calls,1);store.close();
});

test('old stored versions are not deleted when an update fails',async()=>{
  const store=await open();await lib.saveDeviceFile(store,'dataset',item(),body);
  const other=new Uint8Array([...body,33]),newer=item('a',{bytes:other.length,digest:await lib.fileDigest(other)});
  await assert.rejects(lib.ensureDeviceFile({store,run:'dataset',item:newer,download:async()=>{throw Error('offline');}}),/offline/);
  assert.ok(await lib.savedDeviceFile(store,'dataset',item()));store.close();
});

test('digest mismatch never becomes a saved or ready download',async()=>{
  const store=await open();await assert.rejects(lib.saveDeviceFile(store,'dataset',item(),new Uint8Array(body.length)),/校验失败/);
  assert.equal((await store.items('dataset')).length,0);assert.equal(await lib.savedDeviceFile(store,'dataset',item()),null);store.close();
});

test('corrupt local content is detected and repaired by a verified fresh download',async()=>{
  const store=await open();await store.save({key:'dataset:'+digest,bytes:body.length,blob:new Blob([new Uint8Array(body.length)])},{key:'bad',run:'dataset'});
  let calls=0;const result=await lib.ensureDeviceFile({store,run:'dataset',item:item(),download:async()=>{calls++;return body;}});
  assert.equal(calls,1);assert.deepEqual(result.bytes,body);assert.ok(await lib.savedDeviceFile(store,'dataset',item()));store.close();
});

test('a different dataset cannot reuse another dataset download',async()=>{
  const store=await open();await lib.saveDeviceFile(store,'one',item(),body);
  assert.equal(await lib.savedDeviceFile(store,'two',item()),null);assert.deepEqual(await store.items('two'),[]);store.close();
});

test('capability rotation and renamed files reuse bytes without persisting private URLs',async()=>{
  const store=await open();await lib.saveDeviceFile(store,'dataset',item(),body);
  await lib.ensureDeviceFile({store,run:'dataset',item:item('a',{url:'https://new/private/capability',filename:'renamed.pdf'}),download:()=>assert.fail('Unchanged bytes must remain local')});
  const saved=await store.items('dataset');assert.equal(saved[0].filename,'renamed.pdf');assert.ok(!JSON.stringify(saved).includes('https:'));assert.ok(!JSON.stringify(saved).includes('capability'));store.close();
});

test('concurrent reader and bulk download share one transfer and return independent buffers',async()=>{
  const store=await open();let release,calls=0;
  const gate=new Promise(r=>release=r),download=async()=>{calls++;await gate;return body;};
  const first=lib.ensureDeviceFile({store,run:'dataset',item:item(),download});
  const second=lib.ensureDeviceFile({store,run:'dataset',item:item('b'),download});
  await new Promise(r=>setTimeout(r,30));release();
  const [a,b]=await Promise.all([first,second]);assert.equal(calls,1);assert.notEqual(a.bytes.buffer,b.bytes.buffer);
  structuredClone(a.bytes,{transfer:[a.bytes.buffer]});assert.deepEqual(b.bytes,body);store.close();
});

test('cancelling one reader does not cancel a transfer used by another consumer',async()=>{
  const store=await open(),controller=new AbortController();let release,upstream;
  const gate=new Promise(r=>release=r),download=async(url,{signal})=>{upstream=signal;await gate;return body;};
  const first=lib.ensureDeviceFile({store,run:'dataset',item:item(),download,signal:controller.signal});
  const second=lib.ensureDeviceFile({store,run:'dataset',item:item('b'),download});
  await new Promise(r=>setTimeout(r,30));controller.abort();await assert.rejects(first,/abort/i);assert.equal(upstream.aborted,false);
  release();assert.deepEqual((await second).bytes,body);store.close();
});

test('quota failure is explicit, stops bulk update and never evicts previous files',async()=>{
  const store=await open();await lib.saveDeviceFile(store,'dataset',item(),body);
  const originalSave=store.save;store.save=()=>Promise.reject(new DOMException('Device full','QuotaExceededError'));
  const newer=new Uint8Array([...body,50]),other=item('b',{bytes:newer.length,digest:await lib.fileDigest(newer)});
  const result=await lib.updateDeviceLibrary({store,manifest:{run:'dataset',files:[other,item('c')]},download:async()=>newer});
  assert.equal(result.stopped,true);assert.equal(result.failed.length,1);store.save=originalSave;
  assert.ok(await lib.savedDeviceFile(store,'dataset',item()));store.close();
});

test('browser persistence approval or denial is reported without pretending a guarantee',async()=>{
  const denied=await lib.deviceStorageStatus({request:true,storage:{persist:async()=>false,estimate:async()=>({usage:12,quota:50})}});
  assert.equal(denied.persistent,false);assert.equal(denied.quota,50);
  assert.equal((await lib.deviceStorageStatus({request:true,storage:{persist:async()=>true}})).persistent,true);
});
