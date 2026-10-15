export default function({parentElement,data,setTriggerValue}) {
  const root=parentElement.querySelector('.reader-root');
  const registry=globalThis.__plwReaderProbe??=new Map();
  const k=data.run+':'+data.doc;
  let m=registry.get(k);
  if(!m){m={page:data.state.page,zoom:1,rotation:0,pending:null,tool:'rectangle',pdf:null};registry.set(k,m);}
  if(m.base!==data.base){m.pdf=null;m.base=data.base;}
  if(data.ack===m.pending?.id)m.pending=null;
  m.revision=data.revision;m.marks=data.state.marks;m.emit=setTriggerValue;
  let alive=true,viewport=null,pdfPage=null,drawing=null,renderTask=null;
  root.dataset.ready='false';root.dataset.doc=data.doc;
  root.innerHTML='<div class="tools"><button data-cmd="prev">上一页</button><span class="page-no"></span><button data-cmd="next">下一页</button><select aria-label="缩放"><option value="0.5">50%</option><option value="1">100%</option><option value="2">200%</option></select><button data-cmd="rotate">旋转</button><button data-cmd="rectangle">框选</button><button data-cmd="highlight">荧光笔</button><button data-cmd="ink">手写</button><button data-cmd="retry">重试保存</button><span class="read-status"></span></div><div class="read-meta"></div><div class="page-scroll"><div class="paper"><canvas class="pdf-page"></canvas><canvas class="marks"></canvas></div></div>';
  const q=s=>root.querySelector(s),canvas=q('.pdf-page'),overlay=q('.marks'),paper=q('.paper');
  const status=q('.read-status');
  function showStatus(){status.textContent=data.error?'保存失败：'+data.error:m.pending?'保存中…':'已保存';status.classList.toggle('error',!!data.error);}
  showStatus();q('select').value=String(m.zoom);
  function send(action){if(m.pending)return;m.pending={id:crypto.randomUUID(),run:data.run,doc:data.doc,page:m.page,base_revision:m.revision,...action};m.lastSent=m.pending;showStatus();m.emit('action',m.pending);}
  function screen(point){const [x0,y0,x1,y1]=pdfPage.view;return viewport.convertToViewportPoint(x0+point[0]*(x1-x0),y1-point[1]*(y1-y0));}
  function normalized(x,y){const p=viewport.convertToPdfPoint(x,y),[x0,y0,x1,y1]=pdfPage.view;return [(p[0]-x0)/(x1-x0),(y1-p[1])/(y1-y0)];}
  function redraw(extra){
    if(!viewport)return;
    const ctx=overlay.getContext('2d');ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);ctx.clearRect(0,0,viewport.width,viewport.height);
    const marks=[...m.marks.filter(a=>a.page===m.page)];if(extra)marks.push(extra);
    for(const mark of marks){const pts=mark.points.map(screen);ctx.lineWidth=2.5*m.zoom;ctx.strokeStyle='#1576af';
      if(mark.type==='ink'){ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();}
      else {const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y;
        if(mark.type==='highlight'){ctx.fillStyle='#ffd43b66';ctx.fillRect(x,y,w,h);}else ctx.strokeRect(x,y,w,h);}
    }
  }
  let generation=0;
  async function draw(){
    root.dataset.ready='false';
    const current=++generation,started=performance.now();
    try{
      if(renderTask){renderTask.cancel();await renderTask.promise.catch(()=>{});renderTask=null;}
      if(!m.pdf){
        const lib=await import(data.base+'/vendor/build/pdf.mjs');
        lib.GlobalWorkerOptions.workerSrc=data.base+'/vendor/build/pdf.worker.mjs';
        m.library=lib;
        m.pdf=await lib.getDocument({url:data.base+'/pdf/'+data.doc+'.pdf',cMapUrl:data.base+'/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:data.base+'/vendor/standard_fonts/',wasmUrl:data.base+'/vendor/wasm/',isEvalSupported:false}).promise;
      }
      const page=await m.pdf.getPage(m.page);
      if(!alive||current!==generation)return;
      pdfPage=page;viewport=page.getViewport({scale:m.zoom,rotation:(page.rotate+m.rotation)%360});
      for(const c of [canvas,overlay]){c.width=Math.ceil(viewport.width*devicePixelRatio);c.height=Math.ceil(viewport.height*devicePixelRatio);c.style.width=viewport.width+'px';c.style.height=viewport.height+'px';}
      paper.style.width=viewport.width+'px';paper.style.height=viewport.height+'px';
      renderTask=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:[devicePixelRatio,0,0,devicePixelRatio,0,0]});
      await renderTask.promise;
      if(!alive||current!==generation)return;
      redraw();q('.page-no').textContent=m.page+' / '+m.pdf.numPages;
      const text=await page.getTextContent();
      q('.read-meta').textContent=`${Math.round(viewport.width)} × ${Math.round(viewport.height)} · ${m.marks.filter(a=>a.page===m.page).length} 个标记 · ${Math.round(performance.now()-started)} ms`;
      root.dataset.ready='true';root.dataset.page=String(m.page);root.dataset.marks=String(m.marks.length);root.dataset.renderMs=String(performance.now()-started);root.dataset.text=text.items.map(x=>x.str).join(' ');
      root.probe={model:m,viewport,screen,normalized,roundtrip:p=>normalized(...screen(p)),canvas,overlay};
    }catch(e){if(!alive||current!==generation||e.name==='RenderingCancelledException')return;status.textContent='阅读失败：'+e.message;status.classList.add('error');root.dataset.error=e.message;}
  }
  q('select').onchange=e=>{m.zoom=Number(e.target.value);draw();};
  root.querySelectorAll('button').forEach(b=>b.onclick=()=>{
    const c=b.dataset.cmd;
    if(['rectangle','highlight','ink'].includes(c)){m.tool=c;root.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));return;}
    if(c==='retry'){if(m.pending)m.emit('action',m.pending);return;}
    if(m.pending)return;
    if(c==='rotate')m.rotation=(m.rotation+90)%360;
    if(c==='next'||c==='prev'){const next=Math.max(1,Math.min(data.pages,m.page+(c==='next'?1:-1)));if(next===m.page)return;m.page=next;send({kind:'position'});}
    draw();
  });
  overlay.onpointerdown=e=>{if(!viewport||m.pending)return;overlay.setPointerCapture(e.pointerId);const r=overlay.getBoundingClientRect();const p=normalized(e.clientX-r.left,e.clientY-r.top);drawing={type:m.tool,points:[p,p]};};
  overlay.onpointermove=e=>{if(!drawing)return;const r=overlay.getBoundingClientRect();const p=normalized(e.clientX-r.left,e.clientY-r.top).map(n=>Math.max(0,Math.min(1,n)));if(drawing.type==='ink'){if(drawing.points.length<4096)drawing.points.push(p);}else drawing.points[1]=p;redraw(drawing);};
  overlay.onpointerup=()=>{if(!drawing)return;const mark=drawing;drawing=null;send({kind:'mark',type:mark.type,points:mark.points});};
  overlay.onpointercancel=()=>{drawing=null;redraw();};
  draw();
  return ()=>{alive=false;generation++;renderTask?.cancel();};
}
