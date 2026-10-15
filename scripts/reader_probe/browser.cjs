const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const [modules,root]=process.argv.slice(2),{chromium}=require(path.join(modules,'playwright'));
const report={startedAt:new Date().toISOString(),checks:[],externalRequests:[],errors:[],performance:[]};
const safe=u=>{try{return ['127.0.0.1','localhost','[::1]'].includes(new URL(u).hostname)}catch{return false}};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor({timeout:60000});await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');};
const count=async()=>{try{return Object.keys(JSON.parse(await fs.readFile(path.join(root,'annotations.json'),'utf8')).ops).length}catch{return 0}};
async function choose(p,name){
 const file=name.endsWith('（PPT 转换）')?path.join(root,'converted',name.replace('（PPT 转换）','')):path.join(root,'sources',name);
 const sha=crypto.createHash('sha256').update(await fs.readFile(file)).digest('hex');
 await p.getByLabel('合成课件',{exact:true}).fill(name);await p.getByRole('option',{name,exact:true}).click();
 await p.locator(`.reader-root[data-doc="${sha}"][data-ready="true"]`).waitFor();await ready(p);
}
async function goPage(p,n){for(let i=0;i<10;i++){const cur=Number(await p.locator('.reader-root').getAttribute('data-page'));if(cur===n)return;await p.locator(`[data-cmd="${cur>n?'prev':'next'}"]`).click();await p.locator(`.reader-root[data-page="${cur>n?cur-1:cur+1}"][data-ready="true"]`).waitFor();await ready(p);}throw Error('page navigation failed');}
async function draw(p,type){await p.locator(`[data-cmd="${type}"]`).click();const box=await p.locator('canvas.marks').boundingBox();await p.mouse.move(box.x+80,box.y+100);await p.mouse.down();await p.mouse.move(box.x+240,box.y+160,{steps:15});await p.mouse.up();}
(async()=>{
 const context=await chromium.launchPersistentContext(path.join(root,'evidence','browser-'+crypto.randomUUID()),{channel:'msedge',headless:true,viewport:{width:1440,height:1100},args:['--disable-background-networking','--disable-component-update','--no-first-run']});
 try{
  await context.route('**/*',async route=>{if(safe(route.request().url()))await route.continue();else{report.externalRequests.push(route.request().url());await route.abort();}});
  if(context.routeWebSocket)await context.routeWebSocket('**/*',ws=>{if(safe(ws.url()))ws.connectToServer();else{report.externalRequests.push(ws.url());ws.close();}});
  const p=await context.newPage();p.on('pageerror',e=>report.errors.push(e.message));
  await p.goto('http://127.0.0.1:8503');await ready(p);
  await goPage(p,1);
  assert.match(await p.locator('.reader-root').getAttribute('data-text'),/控制原理/);
  await p.screenshot({path:path.join(root,'evidence','native-pdf.png'),fullPage:true});report.checks.push('native PDF Chinese text and canvas');
  for(const type of ['rectangle','highlight','ink']){const before=await count();await draw(p,type);await p.locator('.read-status').filter({hasText:'已保存'}).waitFor();await ready(p);assert.equal(await count(),before+1);}
  await p.screenshot({path:path.join(root,'evidence','annotations.png'),fullPage:true});report.checks.push('rectangle/highlight/ink ACK and disk persistence');
  const before=await count();await p.getByRole('button',{name:'触发页面重跑（仅验证）'}).click();await ready(p);assert.equal(await count(),before);
  await p.locator('.reader-root').evaluate(r=>r.probe.model.emit('action',r.probe.model.lastSent));await ready(p);assert.equal(await count(),before);report.checks.push('rerun and duplicate operation do not duplicate marks');
  await p.getByText('模拟保存失败（仅验证）',{exact:true}).click();await ready(p);assert.equal(await p.getByLabel('模拟保存失败（仅验证）').isChecked(),true);await draw(p,'ink');await p.locator('.read-status.error').waitFor();assert.equal(await count(),before);
  await p.getByText('模拟保存失败（仅验证）',{exact:true}).click();await ready(p);await p.locator('[data-cmd="retry"]').click();await p.locator('.read-status').filter({hasText:'已保存'}).waitFor();await ready(p);assert.equal(await count(),before+1);report.checks.push('save failure reported and same pending stroke retried');
  await goPage(p,2);await p.reload();await ready(p);assert.equal(await p.locator('.reader-root').getAttribute('data-page'),'2');report.checks.push('browser reload restores last committed reading page and marks');
  await choose(p,'旋转 裁剪.pdf');
  await goPage(p,3);
  let maxError=0;
  for(const scale of ['0.5','1','2']){
    await p.getByLabel('缩放',{exact:true}).selectOption(scale);await ready(p);
    for(let turn=0;turn<4;turn++){
      const error=await p.locator('.reader-root').evaluate(r=>Math.max(...[[0,0],[1,1],[.13,.87],[.5,.5]].map(a=>{const b=r.probe.roundtrip(a);return Math.max(Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1]));})));
      maxError=Math.max(maxError,error);await p.locator('[data-cmd="rotate"]').click();await ready(p);
    }
  }
  assert.ok(maxError<1e-12);report.geometryMaxNormalizedError=maxError;report.checks.push('12 zoom/rotation combinations on cropped rotated page');
  await p.setViewportSize({width:1120,height:900});await ready(p);assert.ok((await p.locator('canvas.pdf-page').boundingBox()).width>0);
  for(const name of ['宽屏 合成课件.pdf（PPT 转换）','标准 合成课件.pdf（PPT 转换）','旧格式 合成课件.pdf（PPT 转换）']){
    await choose(p,name);assert.match(await p.locator('.reader-root').getAttribute('data-text'),/控制原理/);
    await p.screenshot({path:path.join(root,'evidence',name+'.png'),fullPage:true});
  }
  report.checks.push('PPTX widescreen/standard and legacy PPT converted PDFs displayed');
  await choose(p,'图片型 PDF.pdf');assert.equal(await p.locator('.reader-root').getAttribute('data-text'),'');
  const beforeScan=await count();await draw(p,'highlight');await p.locator('.read-status').filter({hasText:'已保存'}).waitFor();await ready(p);assert.equal(await count(),beforeScan+1);report.checks.push('image-only PDF supports region highlighting without OCR');
  for(const n of [30,100,300]){const start=Date.now();await choose(p,`性能 ${n}页.pdf`);report.performance.push({pages:n,selection_to_ready_ms:Date.now()-start,render_ms:Number(await p.locator('.reader-root').getAttribute('data-render-ms'))});}
  const source=await p.locator('.reader-root').evaluate(r=>r.probe.model.base);
  const invalid=await p.evaluate(async base=>{const lib=await import(base+'/vendor/build/pdf.mjs');try{await lib.getDocument(base+'/pdf/broken.pdf').promise;return false}catch{return true}},source);
  assert.equal(invalid,true);
  assert.equal((await p.request.get(source+'/../fixtures.json')).status(),404);report.checks.push('malformed PDF rejected and asset path outside allowlist denied');
  const highDpi=await context.browser().newContext({viewport:{width:1280,height:1100},deviceScaleFactor:2});
  await highDpi.route('**/*',async route=>{if(safe(route.request().url()))await route.continue();else{report.externalRequests.push(route.request().url());await route.abort();}});
  if(highDpi.routeWebSocket)await highDpi.routeWebSocket('**/*',ws=>{if(safe(ws.url()))ws.connectToServer();else{report.externalRequests.push(ws.url());ws.close();}});
  const p2=await highDpi.newPage();await p2.goto('http://127.0.0.1:8503');await ready(p2);
  const dpi=await p2.locator('.reader-root').evaluate(r=>({dpr:devicePixelRatio,backing:r.probe.overlay.width,css:r.probe.viewport.width,error:Math.max(...r.probe.roundtrip([.2,.7]).map((v,i)=>Math.abs(v-[.2,.7][i])))}));
  assert.equal(dpi.dpr,2);assert.equal(dpi.backing,Math.ceil(dpi.css*2));assert.ok(dpi.error<1e-12);report.highDpi=dpi;report.checks.push('device pixel ratio 2 canvas and coordinate mapping');await highDpi.close();
  assert.equal(report.externalRequests.length,0);assert.equal(report.errors.length,0);report.passed=true;
 }catch(e){report.failure=e.stack;report.passed=false;const p=context.pages().at(-1);if(p){report.visibleStatus=await p.locator('.read-status').allTextContents().catch(()=>[]);await p.screenshot({path:path.join(root,'evidence','failure.png'),fullPage:true}).catch(()=>{});}throw e;}
 finally{report.finishedAt=new Date().toISOString();await fs.writeFile(path.join(root,'evidence','browser-report.json'),JSON.stringify(report,null,2));await context.close();console.log(JSON.stringify(report,null,2));}
})();
