import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../src/plw/reader/reader.js',import.meta.url),'utf8');
const {downloadReaderPdf:download,downloadCourseware,readerDocument,releaseReaderDocument}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const payload=Buffer.alloc(32768,73),digest=createHash('sha256').update(payload).digest('hex');
const options={bytes:payload.length,digest,idleMs:300,totalMs:5000};
async function server(handler,run){
  const app=http.createServer(handler);await new Promise(r=>app.listen(0,'127.0.0.1',r));
  try{return await run('http://127.0.0.1:'+app.address().port+'/document.pdf');}
  finally{app.closeAllConnections();await new Promise(r=>app.close(r));}
}
function headers(res,length=payload.length,extra={}){res.writeHead(200,{'Content-Type':'application/pdf','Content-Length':length,...extra});}

test('complete file is verified with one request and progress before parsing',async()=>{
  let requests=0;const progress=[];
  await server((req,res)=>{requests++;assert.equal(req.headers.range,undefined);headers(res);res.end(payload);},async url=>{
    const received=await download(url,{...options,onProgress:p=>progress.push(p)});
    assert.deepEqual(Buffer.from(received),payload);assert.equal(requests,1);
    assert.equal(progress.at(-1).verifying,true);assert.equal(progress.at(-1).loaded,payload.length);
  });
});

test('bulk downloads support original PowerPoint bytes with strict MIME and integrity',async()=>{
  const mime='application/vnd.openxmlformats-officedocument.presentationml.presentation';
  await server((req,res)=>{headers(res,payload.length,{'Content-Type':mime});res.end(payload);},async url=>{
    assert.deepEqual(Buffer.from(await downloadCourseware(url,{...options,mime})),payload);
    await assert.rejects(download(url,options),/未返回 PDF/);
  });
});

test('stalled body is aborted and resumes at the exact received offset',async()=>{
  const ranges=[];const split=4096;
  await server((req,res)=>{
    ranges.push(req.headers.range||null);
    if(ranges.length===1){headers(res);res.write(payload.subarray(0,split));return;}
    assert.equal(req.headers.range,`bytes=${split}-${payload.length-1}`);
    res.writeHead(206,{'Content-Type':'application/pdf','Content-Length':payload.length-split,'Content-Range':`bytes ${split}-${payload.length-1}/${payload.length}`});res.end(payload.subarray(split));
  },async url=>{
    const received=await download(url,options);assert.deepEqual(Buffer.from(received),payload);assert.equal(ranges.length,2);
  });
});

test('early connection loss can also resume without duplicating received bytes',async()=>{
  let requests=0;
  await server((req,res)=>{
    requests++;
    if(requests===1){headers(res);res.write(payload.subarray(0,4096));setTimeout(()=>res.destroy(),25);return;}
    const start=Number(/^bytes=(\d+)-/.exec(req.headers.range)?.[1]||0);
    res.writeHead(start?206:200,{'Content-Type':'application/pdf','Content-Length':payload.length-start,...(start?{'Content-Range':`bytes ${start}-${payload.length-1}/${payload.length}`}:{})});res.end(payload.subarray(start));
  },async url=>{assert.deepEqual(Buffer.from(await download(url,options)),payload);assert.equal(requests,2);});
});

for(const [name,respond,pattern] of [
  ['HTML login response',res=>{headers(res,payload.length,{'Content-Type':'text/html'});res.end(payload);},/未返回 PDF/],
  ['expired login',res=>{res.writeHead(401);res.end();},/登录已失效/],
  ['wrong length',res=>{headers(res,4);res.end('test');},/文件大小/],
  ['compressed PDF representation',res=>{headers(res,payload.length,{'Content-Encoding':'gzip'});res.end(payload);},/传输格式/],
  ['wrong digest',res=>{headers(res);res.end(Buffer.alloc(payload.length,74));},/完整性校验/],
  ['redirect to login',res=>{res.writeHead(302,{Location:'/login'});res.end();},/下载中断/],
])test('rejects '+name,async()=>{
  await server((req,res)=>respond(res),async url=>{await assert.rejects(download(url,{...options,maxRetries:0}),pattern);});
});

for(const variant of ['ignored range','wrong offset','changed total'])test('rejects unsafe resume: '+variant,async()=>{
  let requests=0;
  await server((req,res)=>{
    if(++requests===1){headers(res);res.write(payload.subarray(0,4096));return;}
    if(variant==='ignored range'){headers(res);res.end(payload);return;}
    res.writeHead(206,{'Content-Type':'application/pdf','Content-Length':payload.length-4096,
      'Content-Range':`bytes ${variant==='wrong offset'?4095:4096}-${payload.length-1}/${payload.length+(variant==='changed total'?1:0)}`});res.end(payload.subarray(4096));
  },async url=>{await assert.rejects(download(url,options),/续传/);assert.equal(requests,2);});
});

test('repeated stalled connections end with a retry action, never an endless spinner',async()=>{
  let requests=0;const start=Date.now();
  // A valid header followed by no body exercises body timeouts, not just fetch.
  await server((req,res)=>{requests++;headers(res);res.flushHeaders();},async url=>{
    await assert.rejects(download(url,{...options,maxRetries:2}),/重试读取/);assert.equal(requests,3);assert.ok(Date.now()-start<4000);
  });
});

test('document eviction aborts its pending download and permits a clean later load',async()=>{
  const model={};let pendingStarted;
  const began=new Promise(r=>pendingStarted=r);
  await server((req,res)=>{headers(res);res.flushHeaders();pendingStarted();},async url=>{
    const result=readerDocument(model,async signal=>{
      await download(url,{...options,signal});throw Error('Must not start PDF.js after cancellation');
    });
    await began;releaseReaderDocument(model);await assert.rejects(result,/abort/i);assert.equal(model.loading,null);
    const pdf=await readerDocument(model,()=>({promise:Promise.resolve('fresh'),destroy(){}}));assert.equal(pdf,'fresh');
  });
});

test('invalid metadata causes no network request',async()=>{
  let calls=0;
  await assert.rejects(download('http://invalid/',{bytes:1,digest:'bad',fetcher:()=>{calls++;}}),/校验信息/);assert.equal(calls,0);
});

test('does not require the newer AbortSignal.throwIfAborted API',async()=>{
  const saved=AbortSignal.prototype.throwIfAborted;delete AbortSignal.prototype.throwIfAborted;
  try{await server((req,res)=>{headers(res);res.end(payload);},async url=>{
    assert.deepEqual(Buffer.from(await download(url,options)),payload);
  });}finally{AbortSignal.prototype.throwIfAborted=saved;}
});

test('a slow but active connection also has a total time limit',async()=>{
  await server((req,res)=>{
    headers(res);const timer=setInterval(()=>res.write(payload.subarray(0,128)),30);
    res.on('close',()=>clearInterval(timer));
  },async url=>{
    const start=Date.now();await assert.rejects(download(url,{...options,idleMs:300,totalMs:160}),/重试读取/);
    assert.ok(Date.now()-start<1200);
  });
});
