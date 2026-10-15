export default function({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('.reader-root');
  const registry=globalThis.__plwReader??=new Map();
  const key=data.run+':'+data.doc;
  let m=registry.get(key);
  if(m && m.reset!==data.reset){m.pdf?.destroy();registry.delete(key);m=null;}
  if(!m){
    m={page:data.state.page,zoom:1,fit:true,fitMode:'page',rotation:0,pending:null,tool:'pan',pdf:null,reset:data.reset,
      query:'',results:[],searchMessage:'查找课件文字；扫描页可先在“图片文字识别”中离线识别。',textCache:new Map()};
    registry.set(key,m);
    for(const [old,v] of registry){if(old!==key && !v.pending){v.pdf?.destroy();registry.delete(old);}}
  }
  if(data.goto && data.goto.token!==m.gotoToken){m.page=data.goto.page;m.gotoToken=data.goto.token;}
  // A still-open browser can retain the previous component's ephemeral model.
  m.results??=[];m.query??='';m.textCache??=new Map();m.fit??=true;
  m.fitMode??='page';m.thumbCache??=new Map();
  m.searchMessage??='查找课件文字；扫描页可先在“图片文字识别”中离线识别。';
  if(m.base!==data.base){m.pdf?.destroy();m.pdf=null;m.loading=null;m.base=data.base;}
  if(data.ack===m.pending?.id)m.pending=null;
  m.revision=data.revision;m.marks=data.state.marks;m.emit=setTriggerValue;
  let alive=true,viewport=null,pdfPage=null,drawing=null,pan=null,renderTask=null,generation=0,searchGeneration=0,rasterRatio=1;
  let viewRequest=m.viewRequest||{restore:m.viewScroll||{left:0,top:0}},zoomTimer,resizeTimer;
  let thumbEpoch=0,thumbActive=0,thumbQueue=[],thumbObserver;
  const thumbVisible=new Set(),thumbTasks=new Set(),thumbNodes=new Map(),THUMB_CACHE_LIMIT=36;
  root.dataset.ready='false';root.dataset.doc=data.doc;root.tabIndex=0;
  root.setAttribute('aria-label','课件阅读器，左右方向键翻页');
  root.innerHTML=`<div class="tools">
    <div class="tool-group"><button data-cmd="thumbnails" aria-label="页面预览" title="显示或收起页面预览">页面预览</button><button data-cmd="prev" aria-label="上一页">上一页</button><input aria-label="跳转页码" class="jump" type="number" min="1"/><span class="page-total"></span><button data-cmd="jump">跳转</button><button data-cmd="next" aria-label="下一页">下一页</button></div>
    <div class="tool-group zoom-tools"><button data-cmd="zoom-out" aria-label="缩小" title="缩小 10%">−</button><select aria-label="缩放"><option value="fit-page">整页适配</option><option value="fit">适合宽度</option>${[25,33,50,67,75,90,100,110,125,150,175,200,250,300,400].map(v=>`<option value="${v/100}">${v}%</option>`).join('')}<option value="custom" hidden>自定义</option></select><button data-cmd="zoom-in" aria-label="放大" title="放大 10%">＋</button><input type="range" min="25" max="400" step="1" aria-label="缩放比例" title="连续缩放；也可按住 Ctrl 滚动鼠标滚轮"/><span class="zoom-value"></span><button data-cmd="rotate">旋转</button><button data-cmd="focus">专注阅读</button></div>
    <div class="tool-group"><button data-cmd="pan">拖动阅读</button><button data-cmd="rectangle">框选</button><button data-cmd="highlight">荧光笔</button><button data-cmd="ink">手写</button></div>
    <div class="tool-group"><button data-cmd="undo">撤销图形</button><button data-cmd="redo">恢复图形</button><button data-cmd="retry">重试保存</button></div>
  </div><div class="reader-info"><span class="read-meta"></span><span class="read-status" role="status" aria-live="polite"></span></div>
  <details class="search-panel"><summary>查找课件文字</summary><div class="search-tools"><input type="search" aria-label="课件内查找" placeholder="输入文字，回车查找" maxlength="200"/><button data-cmd="search">查找</button><button data-cmd="cancel-search">停止查找</button><button data-cmd="clear-search">清空</button></div><p class="search-status" role="status"></p><div class="search-results"></div></details>
  <div class="reader-body"><nav class="page-thumbnails" aria-label="课件页面预览"></nav><div class="page-stage"><div class="page-scroll"><div class="paper"><canvas class="pdf-page"></canvas><canvas class="marks"></canvas></div></div><button class="page-edge previous" data-cmd="edge-prev" aria-label="阅读区上一页" title="上一页（←）">‹</button><button class="page-edge following" data-cmd="edge-next" aria-label="阅读区下一页" title="下一页（→）">›</button></div></div>`;
  const q=s=>root.querySelector(s),canvas=q('.pdf-page'),overlay=q('.marks'),paper=q('.paper'),scroller=q('.page-scroll');
  const status=q('.read-status'),searchInput=q('[aria-label="课件内查找"]'),thumbList=q('.page-thumbnails');
  function thumbnailLayout(){
    const shown=m.thumbnails??root.clientWidth>720;
    root.classList.toggle('thumbnails-open',shown);thumbList.hidden=!shown;
    q('[data-cmd="thumbnails"]').setAttribute('aria-expanded',String(shown));
  }
  function showStatus(){
    status.textContent=data.error?'保存失败：'+data.error:m.pending?'保存中…':'已保存';
    status.classList.toggle('error',!!data.error);
    q('[data-cmd="retry"]').hidden=!m.pending;
  }
  function syncTools(){
    root.querySelectorAll('[data-cmd]').forEach(b=>{
      const cmd=b.dataset.cmd;
      if(['pan','rectangle','highlight','ink'].includes(cmd))b.setAttribute('aria-pressed',String(m.tool===cmd));
      if(['prev','next','edge-prev','edge-next','jump','undo','redo'].includes(cmd))b.disabled=!!m.pending || (['prev','edge-prev'].includes(cmd)&&m.page===1) || (['next','edge-next'].includes(cmd)&&m.page===data.pages);
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
    for(const [number,button] of thumbNodes){button.setAttribute('aria-current',String(number===m.page));button.disabled=!!m.pending;}
    q('.jump').value=String(m.page);q('.jump').max=String(data.pages);q('.page-total').textContent='/ '+data.pages;
  }
  function send(action){
    if(m.pending)return false;
    m.pending={id:crypto.randomUUID(),run:data.run,doc:data.doc,page:m.page,base_revision:m.revision,...action};
    m.lastSent=m.pending;showStatus();syncTools();m.emit('action',m.pending);return true;
  }
  function go(page){
    if(m.pending||!Number.isInteger(page)||page<1||page>data.pages)return;
    if(page===m.page)return;
    m.page=page;requestView({restore:{left:0,top:0}});
    root.focus({preventScroll:true});
    if(root.clientWidth<=720)m.thumbnails=false;
    thumbnailLayout();revealThumbnail();send({kind:'position'});draw();
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
    if(m.pdf)return m.pdf;
    if(!m.loading)m.loading=(async()=>{
      // Components execute as blob modules. Resolve against the visiting
      // browser's origin so one HTTPS host also works on phones and tablets.
      const assetBase=new URL(data.base,window.location.href).href.replace(/\/$/,'');
      const lib=await import(assetBase+'/vendor/build/pdf.mjs');lib.GlobalWorkerOptions.workerSrc=assetBase+'/vendor/build/pdf.worker.mjs';m.library=lib;
      return await lib.getDocument({url:assetBase+'/pdf/'+data.doc+'.pdf',cMapUrl:assetBase+'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:assetBase+'/vendor/standard_fonts/',wasmUrl:assetBase+'/vendor/wasm/',isEvalSupported:false}).promise;
    })();
    try{m.pdf=await m.loading;return m.pdf;}finally{m.loading=null;}
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
    while(alive&&thumbActive<2&&thumbQueue.length){
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
  async function draw(){
    root.dataset.ready='false';drawing=null;
    const current=++generation,started=performance.now(),pageNumber=m.page;
    try{
      const previous=renderTask;if(previous){previous.cancel();await previous.promise.catch(()=>{});if(renderTask===previous)renderTask=null;}
      const pdf=await documentPdf(),page=await pdf.getPage(pageNumber);
      if(!alive||current!==generation)return;
      if(m.displayedPage&&m.displayedPage!==page)m.displayedPage.cleanup();
      m.displayedPage=page;
      pdfPage=page;
      const rotation=(page.rotate+m.rotation)%360;
      if(m.fit){
        const base=page.getViewport({scale:1,rotation}),padding=getComputedStyle(scroller);
        const width=Math.max(1,scroller.clientWidth-parseFloat(padding.paddingLeft)-parseFloat(padding.paddingRight));
        const height=Math.max(1,scroller.clientHeight-parseFloat(padding.paddingTop)-parseFloat(padding.paddingBottom));
        m.zoom=Math.min(4,width/base.width,m.fitMode==='page'?height/base.height:Infinity);
      }
      viewport=page.getViewport({scale:m.zoom,rotation});
      // Keep large/manual zooms within a bounded raster allocation on tablets.
      rasterRatio=Math.min(devicePixelRatio||1,2,8192/viewport.width,8192/viewport.height,Math.sqrt(8000000/(viewport.width*viewport.height)));
      for(const c of [canvas,overlay]){c.width=Math.ceil(viewport.width*rasterRatio);c.height=Math.ceil(viewport.height*rasterRatio);c.style.width=viewport.width+'px';c.style.height=viewport.height+'px';}
      paper.style.width=viewport.width+'px';paper.style.height=viewport.height+'px';
      restoreView();
      renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:[rasterRatio,0,0,rasterRatio,0,0]});
      await renderTask.promise;if(!alive||current!==generation)return;
      redraw();syncTools();
      const text=await page.getTextContent();if(!alive||current!==generation)return;
      q('.read-meta').textContent=`第 ${m.page} / ${pdf.numPages} 页 · ${m.marks.filter(a=>a.page===m.page).length} 个图形标记 · ← → 翻页 · Ctrl＋滚轮缩放`;
      root.dataset.ready='true';root.dataset.page=String(m.page);root.dataset.marks=String(m.marks.length);root.dataset.renderMs=String(performance.now()-started);root.dataset.text=text.items.map(x=>x.str).join(' ');delete root.dataset.error;
      root.probe={model:m,viewport,screen,normalized,roundtrip:p=>normalized(...screen(p)),canvas,overlay};
    }catch(e){if(!alive||current!==generation||e.name==='RenderingCancelledException')return;status.textContent='阅读失败：'+e.message;status.classList.add('error');root.dataset.error=e.message;}
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
    if(cmd==='retry'){if(m.pending)m.emit('action',m.pending);return;}
    if(cmd==='search'){search();return;}
    if(cmd==='cancel-search'){searchGeneration++;m.searchMessage='已停止查找，保留已找到的匹配页。';root.dataset.searchState='stopped';displayResults();return;}
    if(cmd==='clear-search'){searchGeneration++;m.query='';searchInput.value='';m.results=[];m.searchMessage='查找课件文字；扫描页可先在“图片文字识别”中离线识别。';root.dataset.searchState='idle';displayResults();return;}
    if(cmd==='focus'){
      try{if(document.fullscreenElement)await document.exitFullscreen();else await root.requestFullscreen();}
      catch{m.expanded=!m.expanded;root.classList.toggle('expanded',m.expanded);draw();}
      return;
    }
    if(m.pending)return;
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
    if(!viewport||root.dataset.ready!=='true'||m.pending||e.button!==0)return;
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
  const fullscreen=()=>{q('[data-cmd="focus"]').textContent=document.fullscreenElement?'退出专注':'专注阅读';draw();};
  document.addEventListener('fullscreenchange',fullscreen);
  let width=0,height=0;
  const observer=new ResizeObserver(()=>{
    thumbnailLayout();const nextWidth=scroller.clientWidth,nextHeight=scroller.clientHeight;
    if(Math.abs(width-nextWidth)>2||Math.abs(height-nextHeight)>2){width=nextWidth;height=nextHeight;clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(alive&&m.fit)draw();},90);}
  });observer.observe(scroller);observer.observe(root);
  root.classList.toggle('expanded',!!m.expanded);thumbnailLayout();prepareThumbnails();displayResults();showStatus();syncTools();draw();
  return ()=>{if(root.dataset.searchState==='searching')m.searchMessage='查找已中断，保留已找到的匹配页；可以重新查找。';m.viewScroll={left:scroller.scrollLeft,top:scroller.scrollTop};alive=false;generation++;searchGeneration++;thumbEpoch++;renderTask?.cancel();for(const task of thumbTasks)task.cancel();thumbObserver?.disconnect();observer.disconnect();clearTimeout(resizeTimer);clearTimeout(zoomTimer);scroller.removeEventListener('wheel',wheel);document.removeEventListener('fullscreenchange',fullscreen);};
}
