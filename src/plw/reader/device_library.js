// Explicit device downloads. No time-based expiry, LRU eviction or Cache API.
const DATABASE='plw-device-library-v1';
const inflight=new Map();let defaultStore;
const abort=signal=>{if(signal?.aborted)throw signal.reason||new DOMException('下载已停止','AbortError');};
const fileKey=(run,item)=>run+':'+item.digest;
const itemKey=(run,item)=>run+':'+item.kind+':'+item.id;
export async function fileDigest(bytes){
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
}
function validate(run,item){
  if(!run||!item.id||!['pdf','original'].includes(item.kind)||!Number.isSafeInteger(item.bytes)||item.bytes<0||!(/^[0-9a-f]{64}$/).test(item.digest||''))throw Error('下载文件信息无效');
}
export function openDeviceLibrary({factory=globalThis.indexedDB,name=DATABASE}={}){
  if(!factory)return Promise.reject(Error('此浏览器不支持设备下载库，请使用普通浏览模式'));
  return new Promise((resolve,reject)=>{
    const request=factory.open(name,1);let blocked=false;
    request.onupgradeneeded=()=>{const db=request.result;db.createObjectStore('files',{keyPath:'key'});db.createObjectStore('items',{keyPath:'key'});};
    request.onerror=()=>reject(request.error);
    request.onblocked=()=>{blocked=true;reject(Error('设备下载库正被另一个旧窗口占用，请关闭旧窗口后重试'));};
    request.onsuccess=()=>{
      const db=request.result;if(blocked){db.close();return;}
      const closed=()=>{if(name===DATABASE)defaultStore=null;};
      db.onversionchange=()=>{db.close();closed();};db.onclose=closed;
      const execute=(stores,mode,work)=>new Promise((done,fail)=>{
        let result;const tx=db.transaction(stores,mode);
        tx.oncomplete=()=>done(result);tx.onabort=()=>fail(tx.error||Error('本机文件保存未完成'));
        tx.onerror=()=>{};
        try{work(tx,v=>result=v);}catch(e){tx.abort();fail(e);}
      });
      resolve({name,close:()=>{db.close();closed();},
        file:key=>execute(['files'],'readonly',(tx,set)=>{const r=tx.objectStore('files').get(key);r.onsuccess=()=>set(r.result);}),
        items:run=>execute(['items'],'readonly',(tx,set)=>{const r=tx.objectStore('items').getAll();r.onsuccess=()=>set(r.result.filter(v=>v.run===run));}),
        save:(file,item)=>execute(['files','items'],'readwrite',tx=>{tx.objectStore('files').put(file);tx.objectStore('items').put(item);}),
        describe:item=>execute(['items'],'readwrite',tx=>tx.objectStore('items').put(item)),
      });
    };
  });
}
export function deviceLibrary(){
  return defaultStore??=openDeviceLibrary().catch(error=>{defaultStore=null;throw error;});
}
function descriptor(run,item){
  // Capability URLs and server paths deliberately never enter device storage.
  return{key:itemKey(run,item),run,id:item.id,kind:item.kind,digest:item.digest,bytes:item.bytes,
    filename:item.filename||'课件.pdf',course:item.course||'',savedAt:new Date().toISOString()};
}
export async function savedDeviceFile(store,run,item,{asBytes=false}={}){
  validate(run,item);const record=await store.file(fileKey(run,item));
  if(!record||record.bytes!==item.bytes||record.blob?.size!==item.bytes)return null;
  const bytes=new Uint8Array(await record.blob.arrayBuffer());
  if(await fileDigest(bytes)!==item.digest)return null;
  await store.describe(descriptor(run,item));return asBytes?bytes:record.blob;
}
export async function saveDeviceFile(store,run,item,bytes){
  validate(run,item);
  if(bytes.byteLength!==item.bytes||await fileDigest(bytes)!==item.digest)throw Error('文件完整性校验失败，未保存到设备');
  const blob=new Blob([bytes],{type:item.mime||'application/pdf'});
  await store.save({key:fileKey(run,item),run,digest:item.digest,bytes:item.bytes,blob},descriptor(run,item));
  return blob;
}
export async function ensureDeviceFile({store,run,item,download,signal,onProgress=()=>{}}){
  abort(signal);const local=await savedDeviceFile(store,run,item,{asBytes:true});abort(signal);
  if(local){onProgress({local:true,loaded:item.bytes,total:item.bytes});return{bytes:local,local:true};}
  const key=store.name+':'+fileKey(run,item);let entry=inflight.get(key);
  if(!entry){
    entry={controller:new AbortController(),users:new Set()};inflight.set(key,entry);
    entry.promise=(async()=>{
      const bytes=await download(item.url,{bytes:item.bytes,digest:item.digest,mime:item.mime,signal:entry.controller.signal,
        onProgress:p=>{for(const user of entry.users)user.progress(p);}});
      abort(entry.controller.signal);return saveDeviceFile(store,run,item,bytes);
    })().finally(()=>{if(inflight.get(key)===entry)inflight.delete(key);});
    // A caller may cancel between acquiring a request and attaching its waiter.
    entry.promise.catch(()=>{});
  }
  const user={progress:onProgress};entry.users.add(user);
  let cancel;
  try{
    const blob=await Promise.race([entry.promise,new Promise((_,reject)=>{
      cancel=()=>reject(signal.reason||new DOMException('下载已停止','AbortError'));
      signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
    })]);
    abort(signal);await store.describe(descriptor(run,item));
    return{bytes:new Uint8Array(await blob.arrayBuffer()),local:false};
  }finally{
    signal?.removeEventListener('abort',cancel);entry.users.delete(user);
    if(!entry.users.size&&inflight.get(key)===entry){inflight.delete(key);entry.controller.abort();}
  }
}
export async function updateDeviceLibrary({store,manifest,download,signal,onProgress=()=>{}}){
  const result={downloaded:0,reused:0,failed:[],stopped:false};
  for(let index=0;index<manifest.files.length;index++){
    const item=manifest.files[index];if(signal?.aborted){result.stopped=true;break;}
    try{
      const file=await ensureDeviceFile({store,run:manifest.run,item,download,signal,
        onProgress:p=>onProgress({...p,index,totalFiles:manifest.files.length,item})});
      result[file.local?'reused':'downloaded']++;
    }catch(error){
      if(signal?.aborted){result.stopped=true;break;}
      result.failed.push({id:item.id,filename:item.filename,message:error.message});
      if(error.name==='QuotaExceededError'){result.stopped=true;break;}
    }
    onProgress({index:index+1,totalFiles:manifest.files.length,completed:true,result,item});
  }
  return result;
}
export async function deviceStorageStatus({request=false,storage=globalThis.navigator?.storage}={}){
  let persistent=false;
  try{persistent=request&&storage?.persist?await storage.persist():!!(await storage?.persisted?.());}catch{}
  let estimate={};try{estimate=await storage?.estimate?.()||{};}catch{}
  return{persistent,usage:estimate.usage,quota:estimate.quota};
}
