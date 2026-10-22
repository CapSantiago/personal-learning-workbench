// Usage: node scripts/verify_reader_browser_compat.cjs /path/to/test.pdf
// Requires @napi-rs/canvas (NODE_PATH may point to the bundled dependency directory).
const fs=require('node:fs/promises'),path=require('node:path'),{pathToFileURL}=require('node:url'),{createRequire}=require('node:module'),{Worker}=require('node:worker_threads');
const drawing=require('@napi-rs/canvas');for(const k of ['DOMMatrix','ImageData','Path2D'])globalThis[k]=drawing[k];
class CanvasFactory{create(w,h){const canvas=drawing.createCanvas(w,h);return{canvas,context:canvas.getContext('2d')};}reset(t,w,h){t.canvas.width=w;t.canvas.height=h;}destroy(t){t.canvas=null;t.context=null;}}
(async()=>{
 const repo=path.resolve(__dirname,'..'),vendor=path.join(repo,'assets/pdfjs').replaceAll('\\','/');delete Map.prototype.getOrInsertComputed;delete Uint8Array.prototype.toHex;delete Promise.withResolvers;
 const lib=await import(pathToFileURL(path.join(vendor,'legacy/build/pdf.mjs')).href);
 const thread=new Worker(path.join(__dirname,'reader_compat_worker.mjs'),{workerData:{url:pathToFileURL(path.join(vendor,'legacy/build/pdf.worker.mjs')).href}});
 let task,pdfWorker;try{
 const ready=await new Promise((resolve,reject)=>{thread.on('error',reject);function accept(data){if(data.compatReady){thread.off('message',accept);resolve(data);}}thread.on('message',accept);});
 const listeners=new Map(),port={postMessage:(data,transfer)=>thread.postMessage(data,transfer),addEventListener(type,fn){const listener=data=>fn({data});listeners.set(fn,listener);thread.on(type,listener);},removeEventListener(type,fn){thread.off(type,listeners.get(fn));listeners.delete(fn);}};
 pdfWorker=new lib.PDFWorker({port});const bytes=new Uint8Array(await fs.readFile(process.argv[2]));
 task=lib.getDocument({data:bytes,worker:pdfWorker,CanvasFactory,disableFontFace:true,isEvalSupported:false,cMapUrl:vendor+'/cmaps/',cMapPacked:true,standardFontDataUrl:vendor+'/standard_fonts/',wasmUrl:vendor+'/wasm/'});
 const pdf=await task.promise,results=[];
 for(const n of [...new Set([1,Math.min(15,pdf.numPages),Math.min(25,pdf.numPages)])]){const p=await pdf.getPage(n),v=p.getViewport({scale:.4}),canvas=drawing.createCanvas(Math.ceil(v.width),Math.ceil(v.height));await p.render({canvasContext:canvas.getContext('2d'),viewport:v}).promise;results.push(n);}
 console.log(JSON.stringify({passed:true,separate_worker:true,worker_compatibility:ready,rendered_pages:results}));
 }finally{if(task)await task.destroy();pdfWorker?.destroy();await thread.terminate();}
})().catch(e=>{console.error(e);process.exitCode=1;});
