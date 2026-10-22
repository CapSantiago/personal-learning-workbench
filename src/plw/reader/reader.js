const READER_DOCUMENT_LIMIT=3,READER_BYTE_LIMIT=96*1024*1024;

function checkReaderAbort(signal){
  if(signal?.aborted)throw signal.reason||new DOMException('阅读器加载已取消','AbortError');
}

// Receive and verify the whole file before PDF.js can request pages. This keeps
// network stalls out of page rendering and permits a stalled transfer to resume.
export async function downloadCourseware(url,{bytes,digest,mime='application/pdf',signal,onProgress=()=>{},fetcher=fetch,
  idleMs=15000,totalMs=600000,maxRetries=3}={}){
  if(!Number.isSafeInteger(bytes)||bytes<=0||!(/^[a-f0-9]{64}$/i).test(digest||''))throw new Error('课件校验信息无效，请重新打开课件');
  const output=new Uint8Array(bytes),deadline=Date.now()+totalMs;
  let received=0,retries=0;
  const invalid=message=>Object.assign(new Error(message),{invalidPdfResponse:true});
  while(received<bytes){
    checkReaderAbort(signal);
    const controller=new AbortController();let timer,reader;
    const cancel=()=>controller.abort(signal.reason);
    signal?.addEventListener('abort',cancel,{once:true});
    const arm=()=>{clearTimeout(timer);const remaining=deadline-Date.now();
      if(remaining<=0)throw new Error('课件下载超时，请重试');
      timer=setTimeout(()=>controller.abort(new Error('连接长时间没有收到数据')),Math.min(idleMs,remaining));};
    try{
      arm();onProgress({loaded:received,total:bytes,retries});
      const start=received,response=await fetcher(url,{signal:controller.signal,credentials:'same-origin',
        cache:'no-store',redirect:'error',headers:start?{Range:`bytes=${start}-${bytes-1}`}:{}});
      if(response.status===401||response.status===403)throw invalid('登录已失效，请重新登录后打开课件');
      if(response.status!==200&&response.status!==206)throw invalid('课件下载失败（'+response.status+'），请重新打开课件');
      if(response.redirected||(response.headers.get('content-type')||'').split(';')[0].trim().toLowerCase()!==mime.toLowerCase())throw invalid(mime==='application/pdf'?'服务器未返回 PDF，请重新登录后打开课件':'服务器未返回所需课件文件，请重新登录');
      const encoding=response.headers.get('content-encoding');
      if(encoding&&encoding!=='identity')throw invalid('课件传输格式不正确');
      if(response.status===206){
        const range=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range')||'');
        if(!range||Number(range[1])!==start||Number(range[2])!==bytes-1||Number(range[3])!==bytes)throw invalid('课件续传范围不正确');
      }else if(start)throw invalid('服务器无法续传课件，请重试');
      if(Number(response.headers.get('content-length'))!==bytes-start)throw invalid('课件文件大小不一致');
      if(!response.body)throw invalid('课件响应内容为空');
      reader=response.body.getReader();
      for(;;){
        const {done,value}=await reader.read();
        if(done)break;
        if(value.length>bytes-received)throw invalid('课件文件超出预期大小');
        output.set(value,received);received+=value.length;
        if(value.length){arm();onProgress({loaded:received,total:bytes,retries});}
      }
      if(received!==bytes)throw new Error('课件传输提前结束');
    }catch(error){
      checkReaderAbort(signal);
      if(error.invalidPdfResponse)throw error;
      // Even a connection that keeps failing must reach a visible, retryable end.
      if(++retries>maxRetries||Date.now()>=deadline)throw new Error('课件下载中断，已收到 '+(received/1048576).toFixed(1)+' MB；请点击“重试读取”');
    }finally{
      clearTimeout(timer);signal?.removeEventListener('abort',cancel);
      controller.abort();if(reader){try{await reader.cancel();}catch{}reader.releaseLock();}
    }
  }
  checkReaderAbort(signal);onProgress({loaded:received,total:bytes,retries,verifying:true});
  const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',output));
  const actual=Array.from(hash,v=>v.toString(16).padStart(2,'0')).join('');
  checkReaderAbort(signal);
  if(actual!==digest.toLowerCase())throw new Error('课件完整性校验失败，请点击“重试读取”');
  return output;
}

export function downloadReaderPdf(url,options){return downloadCourseware(url,{...options,mime:'application/pdf'});}

// Serialize durable actions, but never make local navigation await their ACK.
// Only unsent positions are coalesced. A sent action keeps its id on retry.
export function createReaderSaveQueue(model,{send,notify=()=>{},delayMs=300}={}){
  let timer=null,running=false;
  model.queuedPage??=null;model.saveError??='';
  async function flush(){
    clearTimeout(timer);timer=null;
    if(running||model.saveError)return;
    if(!model.pending&&model.queuedPage!==null){
      model.pending={id:crypto.randomUUID(),run:model.run,doc:model.doc,page:model.queuedPage,
        base_revision:model.revision,kind:'position'};model.queuedPage=null;
    }
    const action=model.pending;if(!action){notify();return;}
    running=true;notify();
    try{
      const result=await send(action);
      if(result.ack!==action.id||!Number.isSafeInteger(result.state?.revision)||!Array.isArray(result.state?.marks))throw new Error('保存确认无效，请重试');
      model.revision=result.state.revision;model.marks=result.state.marks;model.pending=null;model.saveError='';
    }catch(error){model.saveError=error.message||'保存未完成，请重试';}
    finally{running=false;notify();if(!model.saveError&&model.queuedPage!==null)void flush();}
  }
  return {
    position(page){model.queuedPage=page;clearTimeout(timer);timer=setTimeout(flush,delayMs);notify();},
    action(action){
      if(model.pending||model.saveError)return false;
      clearTimeout(timer);timer=null;model.queuedPage=null;
      model.pending={id:crypto.randomUUID(),run:model.run,doc:model.doc,page:model.page,base_revision:model.revision,...action};
      void flush();return true;
    },
    retry(){model.saveError='';void flush();},flush,
  };
}

export function rememberPageRaster(model,key,entry,{bytes=32*1024*1024,count=4}={}){
  model.pageRasters??=new Map();model.pageRasters.delete(key);model.pageRasters.set(key,entry);
  const size=()=>[...model.pageRasters.values()].reduce((n,item)=>n+item.bitmap.width*item.bitmap.height*4,0);
  while(model.pageRasters.size>count||size()>bytes){model.pageRasters.delete(model.pageRasters.keys().next().value);}
}

export function releaseReaderDocument(model){
  // Invalidate pending imports/loads as well as an already opened document.
  model.loadEpoch=(model.loadEpoch||0)+1;
  model.downloadController?.abort();model.downloadController=null;
  const resource=model.loadingTask||model.pdf;
  model.pdf=null;model.loading=null;model.loadingTask=null;model.cached=false;
  model.displayedPage=null;model.thumbCache?.clear();model.textCache?.clear();model.pageRasters?.clear();
  if(resource){try{Promise.resolve(resource.destroy()).catch(()=>{});}catch{}}
}

export function trimReaderCache(registry,activeKey){
  const retained=()=>[...registry.values()].filter(v=>v.cached);
  for(const [key,model] of registry){
    const values=retained();
    if(values.length<=READER_DOCUMENT_LIMIT&&values.reduce((n,v)=>n+v.bytes,0)<=READER_BYTE_LIMIT)break;
    if(key===activeKey||!model.cached)continue;
    releaseReaderDocument(model);
    // Keep a small unsaved action model until it can be acknowledged/retried.
    if(!model.pending&&model.queuedPage==null)registry.delete(key);
  }
}

export function selectReaderModel(registry,data){
  const key=data.run+':'+data.doc;
  for(const [old,value] of registry){
    if(value.run!==data.run||value.base!==data.base){releaseReaderDocument(value);registry.delete(old);}
  }
  let model=registry.get(key);
  if(model&&(model.reset!==data.reset||model.digest!==data.digest)){
    releaseReaderDocument(model);registry.delete(key);model=null;
  }
  if(!model)model={page:data.state.page,zoom:1,fit:true,fitMode:'page',rotation:0,pending:null,tool:'pan',pdf:null,
    query:'',results:[],searchMessage:'查找课件文字；扫描页可先在“图片文字识别”中离线识别。',textCache:new Map()};
  Object.assign(model,{run:data.run,doc:data.doc,base:data.base,reset:data.reset,digest:data.digest,cached:true,
    bytes:Number.isSafeInteger(data.bytes)&&data.bytes>0?data.bytes:READER_BYTE_LIMIT});
  registry.delete(key);registry.set(key,model); // Most recently visited last.
  trimReaderCache(registry,key);
  return model;
}

export async function readerDocument(model,start){
  if(model.pdf)return model.pdf;
  if(model.loading)return model.loading;
  const epoch=model.loadEpoch||0;
  const controller=new AbortController();model.downloadController=controller;
  const pending=(async()=>{
    const task=await start(controller.signal);
    if(epoch!==(model.loadEpoch||0)){
      task.promise.catch(()=>{});
      try{await task.destroy();}catch{}
      throw new Error('阅读器已经重新载入');
    }
    model.loadingTask=task;
    const pdf=await task.promise;
    if(epoch!==(model.loadEpoch||0))throw new Error('阅读器已经重新载入');
    model.pdf=pdf;
    return pdf;
  })();
  model.loading=pending;
  try{return await pending;}
  catch(error){
    if(model.loading===pending){
      const failed=model.loadingTask;model.loadingTask=null;
      if(failed){try{Promise.resolve(failed.destroy()).catch(()=>{});}catch{}}
    }
    throw error;
  }finally{if(model.loading===pending){model.loading=null;model.downloadController=null;}}
}

export default function({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('.reader-root');
  const registry=globalThis.__plwReader??=new Map();
  const m=selectReaderModel(registry,data);
  if(data.goto && data.goto.token!==m.gotoToken){m.page=data.goto.page;m.gotoToken=data.goto.token;}
  // A still-open browser can retain the previous component's ephemeral model.
  m.results??=[];m.query??='';m.textCache??=new Map();m.fit??=true;
  m.fitMode??='page';m.thumbCache??=new Map();m.pageRasters??=new Map();m.queuedPage??=null;
  m.searchMessage??='查找课件文字；扫描页可先在“图片文字识别”中离线识别。';
  if(data.ack===m.pending?.id)m.pending=null;
  if(data.revision>=(m.revision??0)){m.revision=data.revision;m.marks=data.state.marks;}
  m.emit=setTriggerValue;
  let alive=true,viewport=null,pdfPage=null,drawing=null,pan=null,renderTask=null,generation=0,searchGeneration=0,rasterRatio=1;
  let viewRequest=m.viewRequest||{restore:m.viewScroll||{left:0,top:0}},zoomTimer,resizeTimer;
  let thumbEpoch=0,thumbActive=0,thumbQueue=[],thumbObserver,prefetchTimer,prefetchTask;
  const thumbVisible=new Set(),thumbTasks=new Set(),thumbNodes=new Map(),THUMB_CACHE_LIMIT=36;
  root.dataset.ready='false';root.dataset.doc=data.doc;root.tabIndex=0;
  root.setAttribute('aria-label','课件阅读器，左右方向键翻页');
  root.innerHTML=`<div class="tools">
    <div class="tool-group"><button data-cmd="thumbnails" aria-label="页面预览" title="显示或收起页面预览">页面预览</button><button data-cmd="prev" aria-label="上一页">上一页</button><input aria-label="跳转页码" class="jump" type="number" min="1"/><span class="page-total"></span><button data-cmd="jump">跳转</button><button data-cmd="next" aria-label="下一页">下一页</button></div>
    <div class="tool-group zoom-tools"><button data-cmd="zoom-out" aria-label="缩小" title="缩小 10%">−</button><select aria-label="缩放"><option value="fit-page">整页适配</option><option value="fit">适合宽度</option>${[25,33,50,67,75,90,100,110,125,150,175,200,250,300,400].map(v=>`<option value="${v/100}">${v}%</option>`).join('')}<option value="custom" hidden>自定义</option></select><button data-cmd="zoom-in" aria-label="放大" title="放大 10%">＋</button><input type="range" min="25" max="400" step="1" aria-label="缩放比例" title="连续缩放；也可按住 Ctrl 滚动鼠标滚轮"/><span class="zoom-value"></span><button data-cmd="rotate">旋转</button><button data-cmd="focus">专注阅读</button></div>
    <div class="tool-group"><button data-cmd="pan">拖动阅读</button><button data-cmd="rectangle">框选</button><button data-cmd="highlight">荧光笔</button><button data-cmd="ink">手写</button></div>
    <div class="tool-group"><button data-cmd="undo">撤销图形</button><button data-cmd="redo">恢复图形</button><button data-cmd="retry">重试保存</button><button data-cmd="retry-read" hidden>重试读取</button></div>
  </div><div class="reader-info"><span class="read-meta"></span><span class="load-status" role="status" aria-live="polite"></span><span class="read-status" role="status" aria-live="polite"></span></div>
  <details class="search-panel"><summary>查找课件文字</summary><div class="search-tools"><input type="search" aria-label="课件内查找" placeholder="输入文字，回车查找" maxlength="200"/><button data-cmd="search">查找</button><button data-cmd="cancel-search">停止查找</button><button data-cmd="clear-search">清空</button></div><p class="search-status" role="status"></p><div class="search-results"></div></details>
  <div class="reader-body"><nav class="page-thumbnails" aria-label="课件页面预览"></nav><div class="page-stage"><div class="page-scroll"><div class="paper"><canvas class="pdf-page"></canvas><canvas class="marks"></canvas></div></div><button class="page-edge previous" data-cmd="edge-prev" aria-label="阅读区上一页" title="上一页（←）">‹</button><button class="page-edge following" data-cmd="edge-next" aria-label="阅读区下一页" title="下一页（→）">›</button></div></div>`;
  const q=s=>root.querySelector(s),canvas=q('.pdf-page'),overlay=q('.marks'),paper=q('.paper'),scroller=q('.page-scroll');
  const status=q('.read-status'),searchInput=q('[aria-label="课件内查找"]'),thumbList=q('.page-thumbnails');
  m.reportLoad=()=>{if(alive)q('.load-status').textContent=m.loadMessage||'';};
  function loading(message){m.loadMessage=message;m.reportLoad?.();}
  function thumbnailLayout(){
    const shown=m.thumbnails??root.clientWidth>720;
    root.classList.toggle('thumbnails-open',shown);thumbList.hidden=!shown;
    q('[data-cmd="thumbnails"]').setAttribute('aria-expanded',String(shown));
  }
  function showStatus(){
    const error=m.saveError||data.error;
    status.textContent=error?'保存待重试：'+error:m.pending||m.queuedPage!==null?'正在后台保存':'已保存';
    status.classList.toggle('error',!!error);
    q('[data-cmd="retry"]').hidden=!error;
  }
  function syncTools(){
    root.querySelectorAll('[data-cmd]').forEach(b=>{
      const cmd=b.dataset.cmd;
      if(['pan','rectangle','highlight','ink'].includes(cmd))b.setAttribute('aria-pressed',String(m.tool===cmd));
      if(['prev','next','edge-prev','edge-next','jump'].includes(cmd))b.disabled=(['prev','edge-prev'].includes(cmd)&&m.page===1) || (['next','edge-next'].includes(cmd)&&m.page===data.pages);
      if(['undo','redo'].includes(cmd))b.disabled=!!m.pending||!!m.saveError;
    });
    overlay.style.touchAction=m.tool==='pan'?'pan-x pan-y':'none';
    q('[data-cmd="focus"]').textContent=document.fullscreenElement||m.expanded?'退出专注':'专注阅读';
    overlay.style.cursor=m.tool==='pan'?'grab':'crosshair';
    const zoom=q('[aria-label="缩放"]'),custom=zoom.querySelector('[value="custom"]');
    custom.textContent=Math.round(m.zoom*100)+'%';
    const preset=[...zoom.options].find(o=>Math.abs(Number(o.value)-m.zoom)<.00001);
    zoom.value=m.fit?(m.fitMode==='page'?'fit-page':'fit'):(preset?.value||'custom');
    q('[aria-label="缩放比例"]').value=String(Math.round(m.zoom*100));q('.zoom-value').textContent=Math.round(m.zoom*100)+'%';
    q('[data-cmd="zoom-out"]').disabled=m.zoom<=.25;q('[data-cmd="zoom-in"]').disabled=m.zoom>=4;
    root.dataset.zoom=String(m.zoom);root.dataset.fitMode=m.fit?m.fitMode:'custom';
    for(const [number,button] of thumbNodes)button.setAttribute('aria-current',String(number===m.page));
    q('.jump').value=String(m.page);q('.jump').max=String(data.pages);q('.page-total').textContent='/ '+data.pages;
  }
  m.reportSave=()=>{if(alive){showStatus();syncTools();redraw();root.dataset.marks=String(m.marks.length);
    if(root.dataset.ready==='true')q('.read-meta').textContent=`第 ${m.page} / ${data.pages} 页 · ${m.marks.filter(a=>a.page===m.page).length} 个图形标记 · ← → 翻页 · Ctrl＋滚轮缩放`;
  }};
  // Same-origin installations use a dedicated authenticated JSON save route.
  // The legacy direct-streamlit launcher keeps its existing trigger path.
  if(data.base.startsWith('/plw-reader/')&&!m.saver){
    m.saver=createReaderSaveQueue(m,{notify:()=>m.reportSave?.(),send:async action=>{
      const body=JSON.stringify(action);
      const response=await fetch(new URL(data.base+'/action/'+data.doc,window.location.href),{
        method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',
        headers:{'Content-Type':'application/json'},body,keepalive:body.length<60000,signal:AbortSignal.timeout(12000)});
      const result=await response.json();if(!response.ok)throw new Error(result.error||'保存失败，请重试');return result;
    }});
    if(m.pending||m.queuedPage!==null)void m.saver.flush();
  }
  function send(action){
    if(m.saver)return m.saver.action(action);
    if(m.pending)return false;
    m.pending={id:crypto.randomUUID(),run:data.run,doc:data.doc,page:m.page,base_revision:m.revision,...action};
    m.lastSent=m.pending;showStatus();syncTools();m.emit('action',m.pending);return true;
  }
  function go(page){
    if((!m.saver&&m.pending)||!Number.isInteger(page)||page<1||page>data.pages)return;
    if(page===m.page)return;
    m.page=page;requestView({restore:{left:0,top:0}});
    root.focus({preventScroll:true});
    if(root.clientWidth<=720)m.thumbnails=false;
    thumbnailLayout();revealThumbnail();if(m.saver)m.saver.position(page);else send({kind:'position'});syncTools();draw();
  }
  function requestView(request){viewRequest=request;m.viewRequest=request;}
  function centerAnchor(clientX,clientY){
    if(!viewport||!pdfPage)return null;
    const box=scroller.getBoundingClientRect(),sheet=paper.getBoundingClientRect();
    const x=clientX??box.left+scroller.clientWidth/2,y=clientY??box.top+scroller.clientHeight/2;
    return {point:normalized(x-sheet.left,y-sheet.top),x:x-box.left,y:y-box.top};
  }
  function setZoom(value,clientX,clientY){
    if(!Number.isFinite(value)||drawing)return;
    const anchor=viewRequest?.anchor||centerAnchor(clientX,clientY);
    m.fit=false;m.zoom=Math.max(.25,Math.min(4,value));requestView({anchor});generation++;renderTask?.cancel();root.dataset.ready='false';syncTools();
    clearTimeout(zoomTimer);zoomTimer=setTimeout(()=>{if(alive)draw();},45);
  }
  function restoreView(){
    const request=viewRequest;viewRequest=null;m.viewRequest=null;
    if(m.fit&&m.fitMode==='page'){scroller.scrollLeft=0;scroller.scrollTop=0;}
    else if(request?.anchor){
      const [x,y]=screen(request.anchor.point),sheet=paper.getBoundingClientRect(),box=scroller.getBoundingClientRect();
      scroller.scrollLeft+=sheet.left+x-box.left-request.anchor.x;
      scroller.scrollTop+=sheet.top+y-box.top-request.anchor.y;
    }else if(request?.restore){scroller.scrollLeft=request.restore.left;scroller.scrollTop=request.restore.top;}
    m.viewScroll={left:scroller.scrollLeft,top:scroller.scrollTop};
  }
  function screen(point){const [x0,y0,x1,y1]=pdfPage.view;return viewport.convertToViewportPoint(x0+point[0]*(x1-x0),y1-point[1]*(y1-y0));}
  function normalized(x,y){const p=viewport.convertToPdfPoint(x,y),[x0,y0,x1,y1]=pdfPage.view;return [(p[0]-x0)/(x1-x0),(y1-p[1])/(y1-y0)];}
  function redraw(extra){
    if(!viewport)return;
    const ctx=overlay.getContext('2d');ctx.setTransform(rasterRatio,0,0,rasterRatio,0,0);ctx.clearRect(0,0,viewport.width,viewport.height);
    const marks=[...m.marks.filter(a=>a.page===m.page)];
    if(m.pending?.kind==='mark'&&m.pending.page===m.page&&!marks.some(a=>a.id===m.pending.id))marks.push(m.pending);
    if(extra)marks.push(extra);
    for(const mark of marks){const pts=mark.points.map(screen);ctx.lineWidth=2.5*m.zoom;ctx.strokeStyle='#1576af';
      if(mark.type==='ink'){ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();}
      else{const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;
        if(mark.type==='highlight'){ctx.fillStyle='#ffd43b66';ctx.fillRect(x,y,w,h);}else ctx.strokeRect(x,y,w,h);}
    }
  }
  async function documentPdf(){
    return readerDocument(m,async signal=>{
      // Components execute as blob modules. Resolve against the visiting
      // browser's origin so one HTTPS host also works on phones and tablets.
      const assetBase=new URL(data.base,window.location.href).href.replace(/\/$/,'');
      loading('正在加载阅读器…');
      const device=await import(assetBase+'/device-library.mjs');
      const lib=await import(assetBase+'/vendor/legacy/build/pdf.mjs');lib.GlobalWorkerOptions.workerSrc=assetBase+'/vendor/legacy/build/pdf.worker.mjs';m.library=lib;
      loading('正在检查本机下载库…');
      const stored=await device.ensureDeviceFile({store:await device.deviceLibrary(),run:data.run,
        item:{id:data.doc,kind:'pdf',bytes:data.bytes,digest:data.digest,mime:'application/pdf',filename:data.filename||'课件.pdf',url:assetBase+'/pdf/'+data.doc+'.pdf'},
        download:downloadReaderPdf,signal,onProgress:({loaded,total,retries,verifying,local})=>
          loading(local?'正在从本机已下载课件读取…':verifying?'正在校验并保存到设备…':`正在下载到设备 · ${(loaded/1048576).toFixed(1)} / ${(total/1048576).toFixed(1)} MB${retries?' · 断点续传 '+retries+'/3':''}`)});
      const bytes=stored.bytes;m.deviceSaved=true;
      checkReaderAbort(signal);loading('正在打开已接收的课件…');
      return lib.getDocument({data:bytes,cMapUrl:assetBase+'/vendor/cmaps/',cMapPacked:true,
        standardFontDataUrl:assetBase+'/vendor/standard_fonts/',wasmUrl:assetBase+'/vendor/wasm/',isEvalSupported:false});
    });
  }
  function revealThumbnail(){
    const button=thumbNodes.get(m.page);if(!button||thumbList.hidden)return;
    const top=button.offsetTop-thumbList.offsetTop,bottom=top+button.offsetHeight;
    if(top<thumbList.scrollTop)thumbList.scrollTop=top;
    else if(bottom>thumbList.scrollTop+thumbList.clientHeight)thumbList.scrollTop=bottom-thumbList.clientHeight;
  }
  function paintThumbnail(number,cached){
    const button=thumbNodes.get(number);if(!alive||!button||!thumbVisible.has(number))return;
    const small=button.querySelector('canvas');small.width=cached.width;small.height=cached.height;
    small.getContext('2d').drawImage(cached,0,0);button.dataset.ready='true';
    button.querySelector('.thumb-frame').style.aspectRatio=`${cached.width} / ${cached.height}`;
  }
  function requestThumbnail(number){
    const key=number+':'+m.rotation,cached=m.thumbCache.get(key);
    if(cached){m.thumbCache.delete(key);m.thumbCache.set(key,cached);paintThumbnail(number,cached);return;}
    if(!thumbQueue.includes(number))thumbQueue.push(number);
    pumpThumbnails();
  }
  function pumpThumbnails(){
    while(alive&&root.dataset.ready==='true'&&thumbActive<2&&thumbQueue.length){
      const number=thumbQueue.shift();if(!thumbVisible.has(number))continue;
      const epoch=thumbEpoch,rotation=m.rotation,key=number+':'+rotation;thumbActive++;
      (async()=>{
        let task,page;
        try{
          const pdf=await documentPdf();page=await pdf.getPage(number);
          if(!alive||epoch!==thumbEpoch)return;
          const base=page.getViewport({scale:1,rotation:(page.rotate+rotation)%360});
          const view=page.getViewport({scale:Math.min(144/base.width,150/base.height),rotation:(page.rotate+rotation)%360});
          const bitmap=document.createElement('canvas');bitmap.width=Math.ceil(view.width);bitmap.height=Math.ceil(view.height);
          task=page.render({canvasContext:bitmap.getContext('2d'),viewport:view});thumbTasks.add(task);await task.promise;
          if(!alive||epoch!==thumbEpoch)return;
          m.thumbCache.set(key,bitmap);
          while(m.thumbCache.size>THUMB_CACHE_LIMIT)m.thumbCache.delete(m.thumbCache.keys().next().value);
          root.dataset.thumbnailCache=String(m.thumbCache.size);paintThumbnail(number,bitmap);
        }catch(e){if(alive&&epoch===thumbEpoch&&e.name!=='RenderingCancelledException'){const button=thumbNodes.get(number);if(button)button.title='预览未完成，仍可点击打开此页';}}
        finally{if(task)thumbTasks.delete(task);if(page&&number!==m.page)page.cleanup();thumbActive--;pumpThumbnails();}
      })();
    }
  }
  function prepareThumbnails(){
    const fragment=document.createDocumentFragment();
    for(let number=1;number<=data.pages;number++){
      const button=document.createElement('button');button.type='button';button.className='thumbnail';button.dataset.page=String(number);
      button.setAttribute('aria-label',`第 ${number} 页预览`);
      button.innerHTML=`<span class="thumb-frame"><canvas width="1" height="1" aria-hidden="true"></canvas></span><span class="thumb-number">${number}</span>`;
      button.onclick=()=>go(number);thumbNodes.set(number,button);fragment.append(button);
    }
    thumbList.append(fragment);
    thumbObserver=new IntersectionObserver(entries=>{
      for(const entry of entries){const number=Number(entry.target.dataset.page);
        if(entry.isIntersecting){thumbVisible.add(number);requestThumbnail(number);}
        else{thumbVisible.delete(number);const small=entry.target.querySelector('canvas');small.width=1;small.height=1;delete entry.target.dataset.ready;}
      }
      root.dataset.thumbnailVisible=String(thumbVisible.size);
    },{root:thumbList,rootMargin:'160px 0px'});
    for(const button of thumbNodes.values())thumbObserver.observe(button);
    revealThumbnail();
  }
  function pageGeometry(page){
    const rotation=(page.rotate+m.rotation)%360;
    let zoom=m.zoom;
    if(m.fit){
      const base=page.getViewport({scale:1,rotation}),padding=getComputedStyle(scroller);
      const width=Math.max(1,Math.floor(scroller.clientWidth-parseFloat(padding.paddingLeft)-parseFloat(padding.paddingRight))-2);
      const height=Math.max(1,Math.floor(scroller.clientHeight-parseFloat(padding.paddingTop)-parseFloat(padding.paddingBottom))-2);
      zoom=Math.min(4,width/base.width,m.fitMode==='page'?height/base.height:Infinity);
    }
    const view=page.getViewport({scale:zoom,rotation});
    const ratio=Math.min(devicePixelRatio||1,2,8192/view.width,8192/view.height,Math.sqrt(8000000/(view.width*view.height)));
    return {viewport:view,ratio,zoom,key:[page.pageNumber,rotation,zoom.toFixed(6),ratio.toFixed(6)].join(':')};
  }
  function cachedRaster(key){
    const entry=m.pageRasters.get(key);
    if(entry){m.pageRasters.delete(key);m.pageRasters.set(key,entry);}
    return entry;
  }
  async function raster(page,geometry,background=false){
    const cached=cachedRaster(geometry.key);if(cached){m.pageCacheHits=(m.pageCacheHits||0)+1;return cached;}
    const bitmap=document.createElement('canvas');bitmap.width=Math.ceil(geometry.viewport.width*geometry.ratio);bitmap.height=Math.ceil(geometry.viewport.height*geometry.ratio);
    const task=page.render({canvasContext:bitmap.getContext('2d'),viewport:geometry.viewport,transform:[geometry.ratio,0,0,geometry.ratio,0,0]});
    if(background)prefetchTask=task;else renderTask=task;
    try{await task.promise;}finally{if(background&&prefetchTask===task)prefetchTask=null;if(!background&&renderTask===task)renderTask=null;}
    const entry={bitmap};rememberPageRaster(m,geometry.key,entry);return entry;
  }
  function prefetchPages(pdf,pageNumber,current){
    clearTimeout(prefetchTimer);
    prefetchTimer=setTimeout(async()=>{
      for(const number of [pageNumber+1,pageNumber-1,pageNumber+2]){
        if(!alive||current!==generation)return;
        if(number<1||number>pdf.numPages)continue;
        try{
          const page=await pdf.getPage(number);if(!alive||current!==generation)return;
          await raster(page,pageGeometry(page),true);
        }catch(error){if(error.name!=='RenderingCancelledException')break;}
        await new Promise(resolve=>setTimeout(resolve,0));
      }
      if(alive&&current===generation)pumpThumbnails();
    },60);
  }
  async function draw(){
    root.dataset.ready='false';drawing=null;clearTimeout(prefetchTimer);prefetchTask?.cancel();
    q('[data-cmd="retry-read"]').hidden=true;
    if(m.pdf)loading(`正在加载第 ${m.page} 页…`);else m.reportLoad();
    const current=++generation,started=performance.now(),pageNumber=m.page;
    try{
      const previous=renderTask;if(previous){previous.cancel();await previous.promise.catch(()=>{});if(renderTask===previous)renderTask=null;}
      const pdf=await documentPdf(),page=await pdf.getPage(pageNumber);
      if(!alive||current!==generation)return;
      const geometry=pageGeometry(page),entry=await raster(page,geometry);
      if(!alive||current!==generation)return;
      // Keep the previous visible page until the new offscreen raster is ready.
      // Drawing and save acknowledgements cannot erase or rebuild this reader.
      pdfPage=page;m.displayedPage=page;viewport=geometry.viewport;rasterRatio=geometry.ratio;m.zoom=geometry.zoom;
      for(const c of [canvas,overlay]){c.width=entry.bitmap.width;c.height=entry.bitmap.height;c.style.width=viewport.width+'px';c.style.height=viewport.height+'px';}
      canvas.getContext('2d').drawImage(entry.bitmap,0,0);
      paper.style.width=viewport.width+'px';paper.style.height=viewport.height+'px';restoreView();loading('');redraw();syncTools();
      q('.read-meta').textContent=`第 ${m.page} / ${pdf.numPages} 页 · ${m.marks.filter(a=>a.page===m.page).length} 个图形标记 · ← → 翻页 · Ctrl＋滚轮缩放`;
      root.dataset.ready='true';root.dataset.page=String(m.page);root.dataset.marks=String(m.marks.length);root.dataset.renderMs=String(performance.now()-started);delete root.dataset.error;
      root.dataset.rasterCache=String(m.pageRasters.size);root.dataset.pageCacheHits=String(m.pageCacheHits||0);
      root.probe={model:m,viewport,screen,normalized,roundtrip:p=>normalized(...screen(p)),canvas,overlay};
      prefetchPages(pdf,pageNumber,current);pumpThumbnails();
      // Text extraction is useful for search/probes, but is not a visual gate.
      page.getTextContent().then(text=>{if(alive&&current===generation)root.dataset.text=text.items.map(x=>x.str).join(' ');}).catch(()=>{});
    }catch(e){if(!alive||current!==generation||e.name==='RenderingCancelledException')return;loading('');status.textContent='阅读失败：'+e.message;status.classList.add('error');root.dataset.error=e.message;q('[data-cmd="retry-read"]').hidden=false;}
  }
  function displayResults(){
    q('.search-status').textContent=m.searchMessage;root.dataset.searchHits=String(m.results.length);
    const list=q('.search-results');list.replaceChildren();
    for(const result of m.results){const button=document.createElement('button');button.type='button';button.className='search-result';button.dataset.page=String(result.page);button.textContent=`第 ${result.page} 页 · ${result.snippet}`;button.onclick=()=>go(result.page);list.append(button);}
  }
  const normalize=text=>text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,'');
  async function search(){
    const query=searchInput.value.trim();if(!query)return;
    const run=++searchGeneration;m.query=query;m.results=[];m.searchOpen=true;m.searchMessage='正在查找…';root.dataset.searchState='searching';displayResults();
    try{
      const pdf=await documentPdf(),needle=normalize(query);let textPages=0,unrecognizedPages=0;
      if(!needle){m.searchMessage='请输入要查找的文字。';root.dataset.searchState='done';displayResults();return;}
      for(let i=1;i<=pdf.numPages;i++){
        if(!alive||run!==searchGeneration)return;
        let text=m.textCache.get(i);
        if(text===undefined){const page=await pdf.getPage(i),content=await page.getTextContent();text=content.items.map(x=>x.str).join(' ');m.textCache.set(i,text);if(m.textCache.size>200)m.textCache.delete(m.textCache.keys().next().value);}
        if(!alive||run!==searchGeneration)return;
        const ocrText=data.ocr_texts?.[String(i)];
        if(!text.trim() && typeof ocrText!=='string')unrecognizedPages++;
        if(typeof ocrText==='string')text+='\n'+ocrText;
        if(text.trim())textPages++;
        const plain=normalize(text),index=plain.indexOf(needle);
        if(index!==-1)m.results.push({page:i,snippet:plain.slice(Math.max(0,index-35),index+100)});
        m.searchMessage=`已查找 ${i} / ${pdf.numPages} 页 · ${m.results.length} 页匹配`;displayResults();
        if(m.results.length===200){m.searchMessage='已列出前 200 个匹配页，请缩小关键词范围。';break;}
        await new Promise(resolve=>setTimeout(resolve,0));
      }
      if(!alive||run!==searchGeneration)return;
      if(!m.results.length)m.searchMessage=textPages?'没有找到匹配文字。':'此课件没有可搜索文字；扫描页请先在“图片文字识别”中进行离线 OCR。';
      if(unrecognizedPages)m.searchMessage+=` 还有 ${unrecognizedPages} 页没有文字层且尚未识别。`;
      root.dataset.searchState='done';displayResults();
    }catch(e){if(alive&&run===searchGeneration){m.searchMessage='查找未完成：'+e.message;root.dataset.searchState='error';displayResults();}}
  }
  searchInput.value=m.query;q('.search-panel').open=!!m.searchOpen;
  q('.search-panel').ontoggle=()=>{m.searchOpen=q('.search-panel').open;};
  searchInput.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search();}};
  q('.jump').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();go(Number(e.target.value));}};
  q('[aria-label="缩放"]').onchange=e=>{
    const value=e.target.value;if(value==='custom')return;
    if(value==='fit'||value==='fit-page'){clearTimeout(zoomTimer);m.fit=true;m.fitMode=value==='fit-page'?'page':'width';requestView({restore:{left:0,top:0}});draw();}
    else setZoom(Number(value));
  };
  q('[aria-label="缩放比例"]').oninput=e=>setZoom(Number(e.target.value)/100);
  const wheel=e=>{if((e.ctrlKey||e.metaKey)&&!drawing){e.preventDefault();setZoom(m.zoom*Math.exp(-Math.max(-100,Math.min(100,e.deltaY))*.002),e.clientX,e.clientY);}};
  scroller.addEventListener('wheel',wheel,{passive:false});
  scroller.onscroll=()=>{if(root.dataset.ready==='true')m.viewScroll={left:scroller.scrollLeft,top:scroller.scrollTop};};
  root.querySelectorAll('[data-cmd]').forEach(b=>b.onclick=async()=>{
    const cmd=b.dataset.cmd;
    if(cmd==='zoom-in'||cmd==='zoom-out'){setZoom(Math.round(m.zoom*100)/100+(cmd==='zoom-in'?.1:-.1));return;}
    if(cmd==='thumbnails'){m.thumbnails=!root.classList.contains('thumbnails-open');thumbnailLayout();revealThumbnail();return;}
    if(['pan','rectangle','highlight','ink'].includes(cmd)){m.tool=cmd;syncTools();return;}
    if(cmd==='retry'){if(m.saver)m.saver.retry();else if(m.pending)m.emit('action',m.pending);return;}
    if(cmd==='retry-read'){showStatus();draw();return;}
    if(cmd==='search'){search();return;}
    if(cmd==='cancel-search'){searchGeneration++;m.searchMessage='已停止查找，保留已找到的匹配页。';root.dataset.searchState='stopped';displayResults();return;}
    if(cmd==='clear-search'){searchGeneration++;m.query='';searchInput.value='';m.results=[];m.searchMessage='查找课件文字；扫描页可先在“图片文字识别”中离线识别。';root.dataset.searchState='idle';displayResults();return;}
    if(cmd==='focus'){
      try{if(document.fullscreenElement)await document.exitFullscreen();else await root.requestFullscreen();}
      catch{m.expanded=!m.expanded;root.classList.toggle('expanded',m.expanded);draw();}
      return;
    }
    if((!m.saver&&m.pending))return;
    if(cmd==='undo'||cmd==='redo'){send({kind:cmd});return;}
    if(cmd==='jump'){go(Number(q('.jump').value));return;}
    if(['prev','next','edge-prev','edge-next'].includes(cmd)){go(m.page+(cmd.endsWith('next')?1:-1));return;}
    if(cmd==='rotate'){
      requestView({anchor:centerAnchor()});m.rotation=(m.rotation+90)%360;thumbEpoch++;thumbQueue=[];
      for(const task of thumbTasks)task.cancel();for(const number of thumbVisible)requestThumbnail(number);
      draw();
    }
  });
  root.onkeydown=e=>{
    const target=e.composedPath()[0];if(e.altKey||e.ctrlKey||e.metaKey||['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable)return;
    if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();go(m.page+(e.key==='ArrowRight'?1:-1));}
  };
  overlay.onpointerdown=e=>{
    if(!viewport||root.dataset.ready!=='true'||e.button!==0||(m.tool!=='pan'&&(m.pending||m.saveError)))return;
    root.focus({preventScroll:true});
    if(m.tool==='pan'){
      if(e.pointerType==='touch')return;
      overlay.setPointerCapture(e.pointerId);pan={x:e.clientX,y:e.clientY,left:scroller.scrollLeft,top:scroller.scrollTop};overlay.style.cursor='grabbing';return;
    }
    e.preventDefault();overlay.setPointerCapture(e.pointerId);const r=overlay.getBoundingClientRect();const p=normalized(e.clientX-r.left,e.clientY-r.top).map(n=>Math.max(0,Math.min(1,n)));drawing={type:m.tool,points:[p,p]};
  };
  overlay.onpointermove=e=>{
    if(pan){scroller.scrollLeft=pan.left+pan.x-e.clientX;scroller.scrollTop=pan.top+pan.y-e.clientY;return;}
    if(!drawing)return;const r=overlay.getBoundingClientRect();const p=normalized(e.clientX-r.left,e.clientY-r.top).map(n=>Math.max(0,Math.min(1,n)));
    if(drawing.type==='ink'){if(drawing.points.length<4096)drawing.points.push(p);}else drawing.points[1]=p;redraw(drawing);
  };
  overlay.onpointerup=()=>{if(pan){pan=null;syncTools();return;}if(!drawing)return;const mark=drawing;drawing=null;send({kind:'mark',type:mark.type,points:mark.points});};
  overlay.onpointercancel=()=>{pan=null;drawing=null;syncTools();redraw();};
  const flushSave=()=>{void m.saver?.flush();};
  window.addEventListener('pagehide',flushSave);
  const fullscreen=()=>{q('[data-cmd="focus"]').textContent=document.fullscreenElement?'退出专注':'专注阅读';draw();};
  document.addEventListener('fullscreenchange',fullscreen);
  let width=0,height=0;
  const observer=new ResizeObserver(()=>{
    thumbnailLayout();const nextWidth=scroller.clientWidth,nextHeight=scroller.clientHeight;
    if(Math.abs(width-nextWidth)>2||Math.abs(height-nextHeight)>2){width=nextWidth;height=nextHeight;clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(alive&&m.fit)draw();},90);}
  });observer.observe(scroller);observer.observe(root);
  root.classList.toggle('expanded',!!m.expanded);thumbnailLayout();prepareThumbnails();displayResults();showStatus();syncTools();draw();
  return ()=>{if(root.dataset.searchState==='searching')m.searchMessage='查找已中断，保留已找到的匹配页；可以重新查找。';m.viewScroll={left:scroller.scrollLeft,top:scroller.scrollTop};alive=false;generation++;searchGeneration++;thumbEpoch++;clearTimeout(prefetchTimer);prefetchTask?.cancel();renderTask?.cancel();for(const task of thumbTasks)task.cancel();thumbObserver?.disconnect();observer.disconnect();clearTimeout(resizeTimer);clearTimeout(zoomTimer);scroller.removeEventListener('wheel',wheel);window.removeEventListener('pagehide',flushSave);flushSave();document.removeEventListener('fullscreenchange',fullscreen);};
}
