const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,root]=process.argv.slice(2),{chromium}=require(path.join(modules,'playwright'));
const out=path.join(root,'evidence'),report={started:new Date().toISOString(),checks:[],external:[],errors:[]};
const idle=async p=>{await p.waitForTimeout(200);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);};
async function pageNumber(p,n){await p.getByLabel('跳转页码',{exact:true}).fill(String(n));await p.locator('[data-cmd="jump"]').click();await p.locator(`.reader-root[data-page="${n}"][data-ready="true"]`).waitFor();await ready(p);}
async function choose(p,name,id){await p.getByLabel('选择课件',{exact:true}).click();await p.getByLabel('选择课件',{exact:true}).fill(name);await p.getByRole('option',{name,exact:true}).click();await p.locator(`.reader-root[data-doc="${id}"][data-ready="true"]`).waitFor();await ready(p);}
async function drag(p){await p.locator('canvas.marks').scrollIntoViewIfNeeded();const b=await p.locator('canvas.marks').boundingBox();const y=Math.max(150,b.y+80);await p.mouse.move(b.x+90,y);await p.mouse.down();await p.mouse.move(b.x+260,y+70,{steps:10});await p.mouse.up();}
async function search(p,text){if(!(await p.getByLabel('课件内查找',{exact:true}).isVisible()))await p.locator('.search-panel summary').click();await p.getByLabel('课件内查找',{exact:true}).fill(text);await p.locator('[data-cmd="search"]').click();await p.locator('.reader-root[data-search-state="done"]').waitFor();}
(async()=>{
 const setup=JSON.parse(await fs.readFile(path.join(out,'setup.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking']});
 const context=await browser.newContext({viewport:{width:1440,height:1100}});
 await context.route('**/*',async r=>{if(new URL(r.request().url()).hostname==='127.0.0.1')await r.continue();else{report.external.push(r.request().url());await r.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).hostname==='127.0.0.1')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.on('pageerror',e=>report.errors.push(e.message));p.setDefaultTimeout(30000);
 try{
  await p.goto('http://127.0.0.1:8505');await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  await p.getByTestId('stSidebar').getByRole('button',{name:'课程书架',exact:true}).click();await idle(p);if(setup.courses){await p.getByLabel('选择课程',{exact:true}).click();await p.getByRole('option',{name:'自动控制原理',exact:true}).click();}await ready(p);
  await choose(p,'原生 PDF 中文课件.pdf',setup.editions['原生 PDF 中文课件.pdf']);await pageNumber(p,1);
  const initial=await p.locator('.reader-root').evaluate(r=>({top:r.getBoundingClientRect().top,tool:r.probe.model.tool,marks:r.dataset.marks,fit:r.probe.model.fit}));
  assert.equal(initial.tool,'pan');assert.equal(initial.fit,true);assert.ok(initial.top<650,JSON.stringify(initial));
  await drag(p);await idle(p);assert.equal(await p.locator('.reader-root').getAttribute('data-marks'),initial.marks);report.checks.push('compact reader above fold and drag mode creates no mark');
  await p.locator('.reader-root').focus();await p.keyboard.press('ArrowRight');await p.locator('.reader-root[data-page="2"][data-ready="true"]').waitFor();await ready(p);
  await p.locator('.reader-root').focus();await p.keyboard.press('ArrowLeft');await p.locator('.reader-root[data-page="1"][data-ready="true"]').waitFor();await ready(p);report.checks.push('scoped keyboard page navigation');
  await search(p,'页面 2');assert.equal(await p.locator('.search-result[data-page="2"]').count(),1);
  await p.locator('.search-result[data-page="2"]').click();await p.locator('.reader-root[data-page="2"][data-ready="true"]').waitFor();await ready(p);
  const count=await p.locator('.search-result').count();assert.ok(count>0);
  await p.getByLabel('课件内查找',{exact:true}).focus();await p.keyboard.press('ArrowRight');assert.equal(await p.locator('.reader-root').getAttribute('data-page'),'2');
  await search(p,'<img src=x onerror=alert(1)>');assert.equal(await p.locator('.search-result').count(),0);assert.equal(await p.locator('.reader-root img').count(),0);
  await search(p,'控制原理');assert.equal(await p.locator('.search-result').count(),3);report.checks.push('offline text search, Chinese whitespace matching, safe snippets, page jump and input keys');
  await p.locator('.search-panel summary').click();
  await p.locator('[data-cmd="focus"]').click();await p.waitForFunction(()=>!!document.fullscreenElement);await ready(p);
  const before=Number(await p.locator('.reader-root').getAttribute('data-marks'));
  await p.locator('[data-cmd="rectangle"]').click();await drag(p);await p.locator(`.reader-root[data-marks="${before+1}"][data-ready="true"]`).waitFor();await ready(p);
  assert.equal(await p.evaluate(()=>!!document.fullscreenElement),true);
  assert.equal(await p.locator('[data-cmd="focus"]').innerText(),'退出专注');
  await p.locator('.reader-root').screenshot({path:path.join(out,'focused-reader.png')});
  await p.locator('[data-cmd="focus"]').click();await p.waitForFunction(()=>!document.fullscreenElement);await ready(p);report.checks.push('fullscreen remains active across annotation save and exits normally');
  await p.getByLabel('缩放',{exact:true}).selectOption('fit');await p.setViewportSize({width:1100,height:900});await ready(p);
  const fit=await p.locator('.reader-root').evaluate(r=>({canvas:r.probe.viewport.width,available:r.querySelector('.page-scroll').clientWidth-40,error:Math.max(...r.probe.roundtrip([.2,.7]).map((n,i)=>Math.abs(n-[.2,.7][i])))}));
  assert.ok(fit.canvas<=fit.available+2);assert.ok(fit.error<1e-12);report.fit=fit;
  await p.setViewportSize({width:1440,height:1100});await ready(p);
  await choose(p,'旋转 裁剪.pdf',setup.editions['旋转 裁剪.pdf']);await pageNumber(p,3);
  let max=0;for(const zoom of ['0.5','1','2']){await p.getByLabel('缩放',{exact:true}).selectOption(zoom);await ready(p);for(let i=0;i<4;i++){const err=await p.locator('.reader-root').evaluate(r=>Math.max(...[[0,0],[1,1],[.2,.7]].flatMap(v=>r.probe.roundtrip(v).map((x,j)=>Math.abs(x-v[j])))));max=Math.max(max,err);await p.locator('[data-cmd="rotate"]').click();await ready(p);}}
  assert.ok(max<1e-12);report.geometryError=max;report.checks.push('responsive fit and 12 zoom/rotation coordinate checks');
  await choose(p,'图片型 PDF.pdf',setup.editions['图片型 PDF.pdf']);await search(p,'控制');assert.match(await p.locator('.search-status').innerText(),/没有可搜索文字/);report.checks.push('scanned PDF search explains no OCR text');
  await choose(p,'性能 300页.pdf',setup.editions['性能 300页.pdf']);if(!(await p.getByLabel('课件内查找',{exact:true}).isVisible()))await p.locator('.search-panel summary').click();await p.getByLabel('课件内查找',{exact:true}).fill('unlikely_string_123');await p.locator('[data-cmd="search"]').click();await p.locator('[data-cmd="cancel-search"]').click();assert.equal(await p.locator('.reader-root').getAttribute('data-search-state'),'stopped');
  await choose(p,'原生 PDF 中文课件.pdf',setup.editions['原生 PDF 中文课件.pdf']);await p.locator('[data-cmd="pan"]').click();
  await p.locator('.reader-root').evaluate(r=>{const m=r.probe.model;delete m.results;delete m.textCache;delete m.query;delete m.fit;});
  await pageNumber(p,1);await pageNumber(p,2);
  assert.equal(await p.locator('.reader-root').evaluate(r=>r.probe.model.fit),true);report.checks.push('previous component model upgrades safely after rerun');
  await p.locator('.reader-root').screenshot({path:path.join(out,'compact-reader.png')});report.checks.push('300-page search cancellation and safe courseware switching');
  const marks=await p.locator('.reader-root').getAttribute('data-marks');await p.reload();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);await p.getByTestId('stSidebar').getByRole('button',{name:'课程书架',exact:true}).click();await idle(p);if(setup.courses){await p.getByLabel('选择课程',{exact:true}).click();await p.getByRole('option',{name:'自动控制原理',exact:true}).click();}await ready(p);
  assert.equal(await p.locator('.reader-root').getAttribute('data-page'),'2');assert.equal(await p.locator('.reader-root').getAttribute('data-marks'),marks);report.checks.push('reader optimization preserves saved page and annotations after reload');
  assert.equal(report.external.length,0);assert.equal(report.errors.length,0);report.passed=true;
 }catch(e){report.passed=false;report.failure=e.stack;report.body=(await p.locator('body').innerText()).slice(-5000);await p.screenshot({path:path.join(out,'polish-failure.png')});throw e;}
 finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'reader-polish-browser.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
})();


