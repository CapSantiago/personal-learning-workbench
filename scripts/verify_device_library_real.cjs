// Isolated real-file integration test. Config supplies a disposable authenticated
// loopback server, never a cloud account. The driver stops it after the download.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url'),{Worker}=require('node:worker_threads');
const drawing=require('@napi-rs/canvas');
const {IDBFactory}=require('../.sandbox/device-library-test-runtime/node_modules/fake-indexeddb');
for(const key of ['DOMMatrix','ImageData','Path2D'])globalThis[key]=drawing[key];
class CanvasFactory{create(w,h){const canvas=drawing.createCanvas(w,h);return{canvas,context:canvas.getContext('2d')};}reset(t,w,h){t.canvas.width=w;t.canvas.height=h;}destroy(t){t.canvas=null;t.context=null;}}
(async()=>{
 const repo=path.resolve(__dirname,'..'),folder=process.argv[2],cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8'));
 const source=await fs.readFile(path.join(repo,'src/plw/reader/reader.js'),'utf8');
 const reader=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 const deviceSource=await fs.readFile(path.join(repo,'src/plw/reader/device_library.js'),'utf8');
 const device=await import('data:text/javascript;base64,'+Buffer.from(deviceSource).toString('base64'));
 const factory=new IDBFactory();let store=await device.openDeviceLibrary({factory,name:'real-pdf-reopen'});
 const vendor=path.join(repo,'assets/pdfjs').replaceAll('\\','/');
 delete Map.prototype.getOrInsertComputed;delete Uint8Array.prototype.toHex;delete Promise.withResolvers;
 const lib=await import(pathToFileURL(path.join(vendor,'legacy/build/pdf.mjs')).href);
 const registry=new Map(),threads=[],workers=[],times=[];let loads=0,networkCalls=0;
 const fetcher=(url,options)=>{networkCalls++;return fetch(url,{...options,headers:{...options.headers,Cookie:cfg.cookie}});};
 const metadata=doc=>({run:'isolated-real-file',base:cfg.base,doc,bytes:doc===cfg.doc_a?cfg.size:cfg.size_b,digest:doc===cfg.doc_a?cfg.digest:cfg.digest_b,reset:'',state:{page:1}});
 const file=doc=>({...metadata(doc),id:doc,kind:'pdf',mime:'application/pdf',filename:doc+'.pdf',url:cfg.base+'/pdf/'+doc+'.pdf'});
 const data=new Map();const started=performance.now();
 for(const doc of [cfg.doc_a,cfg.doc_b])await device.ensureDeviceFile({store,run:'isolated-real-file',item:file(doc),download:(url,opts)=>reader.downloadReaderPdf(url,{...opts,fetcher})});
 store.close();
 const downloadMs=Math.round(performance.now()-started);
 const stats=await(await fetch(cfg.origin+'/local-diagnostic/stats',{headers:{Cookie:cfg.cookie}})).json();
 assert.equal(stats.requests,2);assert.equal(stats.hash_calls,2);
 await fs.writeFile(path.join(folder,'downloaded'),JSON.stringify({requests:stats.requests}));
 for(let n=0;;n++){
   try{await fs.access(path.join(folder,'offline'));break;}catch{if(n>300)throw Error('Driver did not stop test server');await new Promise(r=>setTimeout(r,100));}
 }
 // Network is gone before PDF.js opens the document or renders any page.
 await assert.rejects(fetch(cfg.origin+'/local-diagnostic/stats'));
 store=await device.openDeviceLibrary({factory,name:'real-pdf-reopen'});
 for(const doc of [cfg.doc_a,cfg.doc_b])data.set(doc,(await device.ensureDeviceFile({store,run:'isolated-real-file',item:file(doc),download:()=>assert.fail('Reopened download library must not use the network')})).bytes);
 const originalFetch=globalThis.fetch;globalThis.fetch=()=>{throw Error('Unexpected network after full-file download');};
 async function worker(){
   const thread=new Worker(path.join(__dirname,'reader_compat_worker.mjs'),{workerData:{url:pathToFileURL(path.join(vendor,'legacy/build/pdf.worker.mjs')).href}});threads.push(thread);
   await new Promise((resolve,reject)=>{thread.once('error',reject);function ready(d){if(d.compatReady){thread.off('message',ready);resolve();}}thread.on('message',ready);});
   const listeners=new Map(),port={postMessage:(d,t)=>thread.postMessage(d,t),addEventListener(type,fn){const cb=d=>fn({data:d});listeners.set(fn,cb);thread.on(type,cb);},removeEventListener(type,fn){thread.off(type,listeners.get(fn));listeners.delete(fn);}};
   const result=new lib.PDFWorker({port});workers.push(result);return result;
 }
 async function open(doc){
   const model=reader.selectReaderModel(registry,metadata(doc));
   const pdf=await reader.readerDocument(model,async()=>{loads++;return lib.getDocument({data:data.get(doc),worker:await worker(),CanvasFactory,disableFontFace:true,isEvalSupported:false,cMapUrl:vendor+'/cmaps/',cMapPacked:true,standardFontDataUrl:vendor+'/standard_fonts/',wasmUrl:vendor+'/wasm/'});});
   return{model,pdf};
 }
 async function render(pdf,n,scale=.4){
   const start=performance.now(),page=await pdf.getPage(n),view=page.getViewport({scale}),canvas=drawing.createCanvas(Math.ceil(view.width),Math.ceil(view.height));
   await page.render({canvasContext:canvas.getContext('2d'),viewport:view}).promise;
   const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
   let nonWhite=0;for(let i=0;i<pixels.length;i+=4)if(pixels[i]<240||pixels[i+1]<240||pixels[i+2]<240)nonWhite++;
   assert.ok(nonWhite>100,'Page '+n+' should contain rendered content');times.push({page:n,ms:Math.round(performance.now()-start)});return canvas;
 }
 try{
   const a=await open(cfg.doc_a);assert.equal(a.pdf.numPages,54);
   const failedPage=await render(a.pdf,5,1.2);await fs.writeFile(path.join(folder,'page-5.png'),failedPage.toBuffer('image/png'));
   for(let n=1;n<=a.pdf.numPages;n++)await render(a.pdf,n);
   a.model.page=5;a.model.thumbCache=new Map([[5,failedPage]]);
   const b=await open(cfg.doc_b);assert.equal(b.pdf.numPages,35);await render(b.pdf,1);
   const returnStart=performance.now(),again=await open(cfg.doc_a);await render(again.pdf,5,1.2);
   assert.equal(again.model,a.model);assert.equal(again.pdf,a.pdf);assert.equal(again.model.thumbCache.get(5),failedPage);assert.equal(loads,2);assert.equal(networkCalls,2);
   const sorted=times.map(t=>t.ms).sort((a,b)=>a-b);
   const report={passed:true,device_library_reopened:true,persistence_test_engine:'fake-indexeddb',bytes:cfg.size,pages:54,other_pages:35,pdf_sha256:cfg.digest,download_ms:downloadMs,pdf_requests:stats.requests,server_full_hashes:stats.hash_calls,network_disabled_before_parsing:true,separate_workers:true,render_count:times.length,render_p95_ms:sorted[Math.floor(sorted.length*.95)],render_max_ms:sorted.at(-1),return_to_A_ms:Math.round(performance.now()-returnStart),return_new_pdf_requests:0,thumbnail_reused:true,timings:times};
   await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,timings:undefined}));
 }finally{
   store.close();globalThis.fetch=originalFetch;for(const model of registry.values())reader.releaseReaderDocument(model);
   for(const w of workers)w.destroy();for(const t of threads)await t.terminate();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
