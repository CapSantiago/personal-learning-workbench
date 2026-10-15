// Real Edge browser checks; only a synthetic reader-navigation workspace on 8505.
const fs = require('node:fs/promises'), path = require('node:path'), assert = require('node:assert/strict');
const crypto = require('node:crypto');
const [modules, rootArgument] = process.argv.slice(2);
const {chromium} = require(path.join(modules, 'playwright'));
const project = path.resolve(__dirname, '..'), root = path.resolve(rootArgument);
const relative = path.relative(path.join(project, '.sandbox', 'test-runs'), root);
assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Synthetic workspace required');
const base = 'http://127.0.0.1:8505', out = path.join(root, 'evidence');
const report = {started:new Date().toISOString(), checks:[], external:[], errors:[], consoleErrors:[], fits:[], device:'Edge desktop plus phone-sized viewport; not physical iPad Safari'};
const appendCheck=report.checks.push.bind(report.checks);report.checks.push=(...checks)=>{console.log(checks.join('\n'));return appendCheck(...checks);};
const idle = async p => {await p.waitForTimeout(180);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');assert.equal(await p.getByTestId('stException').count(),0);};
const ready = async p => {await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);await p.locator('.reader-root[data-ready="true"]').waitFor();for(let attempt=0;attempt<100;attempt++){if(await p.locator('.reader-root').evaluate(r=>r.probe&&!r.probe.model.pending))return;await p.waitForTimeout(100);}throw new Error('Reader save acknowledgement did not settle');};
const redraw = async p => {await p.waitForTimeout(220);await ready(p);};
async function number(p,n){await p.getByLabel('跳转页码',{exact:true}).fill(String(n));await p.locator('[data-cmd="jump"]').click();await p.locator(`.reader-root[data-page="${n}"][data-ready="true"]`).waitFor();await ready(p);}
async function choose(p,doc){if(await p.locator('.reader-root').getAttribute('data-doc')===doc.edition){await ready(p);return;}await p.getByLabel('选择课件',{exact:true}).click();await p.getByLabel('选择课件',{exact:true}).fill(doc.name);await p.getByRole('option',{name:doc.name,exact:true}).click();await p.locator(`.reader-root[data-doc="${doc.edition}"][data-ready="true"]`).waitFor();await ready(p);}
async function bookshelf(p){const opener=p.getByTestId('stExpandSidebarButton');if(await opener.isVisible())await opener.click();await p.getByTestId('stSidebar').getByRole('button',{name:'课程书架',exact:true}).click();await ready(p);if(p.viewportSize().width<700&&await p.getByTestId('stSidebar').getAttribute('aria-expanded')==='true'){await p.getByTestId('stSidebarCollapseButton').getByRole('button').click();await p.waitForTimeout(350);}}
async function fit(p,label){
  await redraw(p);
  const result=await p.locator('.reader-root').evaluate(r=>{
    const s=r.querySelector('.page-scroll'), paper=r.querySelector('.paper'), c=getComputedStyle(s), b=paper.getBoundingClientRect(), sb=s.getBoundingClientRect();
    const width=s.clientWidth-parseFloat(c.paddingLeft)-parseFloat(c.paddingRight),height=s.clientHeight-parseFloat(c.paddingTop)-parseFloat(c.paddingBottom);
    return {mode:r.dataset.fitMode,zoom:+r.dataset.zoom,width,height,paperWidth:b.width,paperHeight:b.height,
      left:b.left-sb.left,top:b.top-sb.top,scrollWidth:s.scrollWidth,scrollHeight:s.scrollHeight,clientWidth:s.clientWidth,clientHeight:s.clientHeight};
  });
  assert.equal(result.mode,'page',label);assert.ok(result.paperWidth<=result.width+2,`${label}: width ${JSON.stringify(result)}`);assert.ok(result.paperHeight<=result.height+2,`${label}: height ${JSON.stringify(result)}`);
  assert.ok(Math.min(Math.abs(result.paperWidth-result.width),Math.abs(result.paperHeight-result.height))<3,`${label}: maximum proportional fit`);
  assert.ok(result.left>=0&&result.top>=0,label+' entire page visible');assert.ok(result.scrollWidth<=result.clientWidth+2&&result.scrollHeight<=result.clientHeight+2,label+' no clipping scroll');
  report.fits.push({label,...result});
}
async function position(p){return await p.locator('.reader-root').evaluate(r=>{const s=r.querySelector('.page-scroll').getBoundingClientRect(),b=r.querySelector('.paper').getBoundingClientRect();const x=s.left+s.width*.55,y=s.top+s.height*.48;return {x,y,point:r.probe.normalized(x-b.left,y-b.top),zoom:+r.dataset.zoom};});}
async function mark(p){
  await redraw(p);await p.locator('[data-cmd="rectangle"]').click();await p.locator('[data-cmd="rectangle"][aria-pressed="true"]').waitFor();await p.locator('.page-stage').scrollIntoViewIfNeeded();
  const target=await p.locator('.reader-root').evaluate(r=>{const b=r.querySelector('canvas.marks').getBoundingClientRect();return [[.25,.3],[.5,.45]].map(v=>{const s=r.probe.screen(v);return {x:b.left+s[0],y:b.top+s[1]};});});
  const before=Number(await p.locator('.reader-root').getAttribute('data-marks'));
  await p.mouse.move(target[0].x,target[0].y);await p.mouse.down();await p.mouse.move(target[1].x,target[1].y,{steps:8});await p.mouse.up();
  await p.locator(`.reader-root[data-marks="${before+1}"][data-ready="true"]`).waitFor();await ready(p);
  const saved=await p.locator('.reader-root').evaluate(r=>r.probe.model.marks.at(-1));
  assert.equal(saved.type,'rectangle');assert.equal(saved.page,3);
  assert.ok(Math.max(...saved.points.flatMap((a,i)=>a.map((v,j)=>Math.abs(v-[[.25,.3],[.5,.45]][i][j]))))<.012,'real drawing uses canonical cropped/rotated coordinates');
  return saved;
}
(async()=>{
  const setup=JSON.parse(await fs.readFile(path.join(out,'setup.json'),'utf8'));assert.equal(path.resolve(setup.root),root);
  const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
  const context=await browser.newContext({viewport:{width:1600,height:1100}});
  await context.route('**/*',async r=>{if(new URL(r.request().url()).origin===base)await r.continue();else{report.external.push(r.request().url());await r.abort();}});
  await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).origin==='ws://127.0.0.1:8505')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
  const p=await context.newPage();p.setDefaultTimeout(30000);p.on('pageerror',e=>report.errors.push(e.message));p.on('console',m=>{if(m.type()==='error')report.consoleErrors.push(m.text());});
  try{
    await p.goto(base);await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);await bookshelf(p);await choose(p,setup.documents.mixed);await number(p,1);
    assert.equal(await p.getByLabel('缩放',{exact:true}).inputValue(),'fit-page');assert.equal(await p.locator('.page-thumbnails').isVisible(),true);
    for(let n=1;n<=5;n++){await number(p,n);await fit(p,'page '+n);}
    await number(p,3);for(let n=0;n<4;n++){await p.locator('[data-cmd="rotate"]').click();await fit(p,'rotated crop '+(n+1));}
    await p.setViewportSize({width:1190,height:820});await fit(p,'resized 1190x820');await p.setViewportSize({width:1600,height:1100});await fit(p,'restored desktop');
    report.checks.push('Landscape, portrait, intrinsic crop/rotation, four user rotations and window resizing preserve complete proportional page fit');

    await p.getByLabel('缩放',{exact:true}).selectOption('fit');await redraw(p);
    const widthFit=await p.locator('.reader-root').evaluate(r=>{const s=r.querySelector('.page-scroll'),c=getComputedStyle(s);return {w:r.probe.viewport.width,available:s.clientWidth-parseFloat(c.paddingLeft)-parseFloat(c.paddingRight),mode:r.dataset.fitMode};});
    assert.equal(widthFit.mode,'width');assert.ok(Math.abs(widthFit.w-widthFit.available)<3);report.checks.push('Fit-width remains available');

    await p.getByLabel('缩放',{exact:true}).selectOption('1.5');await redraw(p);await p.locator('.page-stage').scrollIntoViewIfNeeded();
    const anchor=await position(p);await p.mouse.move(anchor.x,anchor.y);await p.keyboard.down('Control');await p.mouse.wheel(0,-160);await p.keyboard.up('Control');await redraw(p);
    const anchored=await p.locator('.reader-root').evaluate((r,a)=>{const b=r.querySelector('.paper').getBoundingClientRect(),s=r.probe.screen(a.point);return {x:b.left+s[0],y:b.top+s[1],zoom:+r.dataset.zoom};},anchor);
    assert.ok(anchored.zoom>anchor.zoom);assert.ok(Math.hypot(anchored.x-anchor.x,anchored.y-anchor.y)<3,`wheel anchor ${JSON.stringify({anchor,anchored})}`);
    report.wheel={before:anchor,after:anchored};report.checks.push('Actual Ctrl+wheel zoom preserves PDF point under mouse cursor');

    const slider=p.getByLabel('缩放比例',{exact:true});await slider.scrollIntoViewIfNeeded();const box=await slider.boundingBox();await p.mouse.click(box.x+box.width*.34,box.y+box.height/2);await redraw(p);
    const slideBefore=Number(await slider.inputValue());await slider.focus();await p.keyboard.press('ArrowRight');await redraw(p);
    assert.equal(Number(await slider.inputValue()),slideBefore+1);assert.ok(Math.abs(Number(await p.locator('.reader-root').getAttribute('data-zoom'))-(slideBefore+1)/100)<.0001);
    await p.locator('[data-cmd="zoom-in"]').click();await redraw(p);assert.equal(Number(await slider.inputValue()),slideBefore+11);
    await p.locator('[data-cmd="zoom-out"]').click();await redraw(p);assert.equal(Number(await slider.inputValue()),slideBefore+1);
    await slider.focus();await p.keyboard.press('Home');await redraw(p);assert.equal(Number(await slider.inputValue()),25);assert.equal(await p.locator('[data-cmd="zoom-out"]').isDisabled(),true);
    await slider.focus();await p.keyboard.press('End');await redraw(p);assert.equal(Number(await slider.inputValue()),400);assert.equal(await p.locator('[data-cmd="zoom-in"]').isDisabled(),true);
    report.checks.push('Actual slider, 1% keyboard steps, +/- 10% controls and 25%–400% limits');

    await p.getByLabel('缩放',{exact:true}).selectOption('fit-page');await redraw(p);
    await p.locator('.thumbnail[data-page="4"]').click();await p.locator('.reader-root[data-page="4"][data-ready="true"]').waitFor();await ready(p);
    assert.equal(await p.locator('.thumbnail[data-page="4"]').getAttribute('aria-current'),'true');
    await p.locator('[data-cmd="edge-next"]').click();await p.locator('.reader-root[data-page="5"][data-ready="true"]').waitFor();await ready(p);assert.equal(await p.locator('[data-cmd="edge-next"]').isDisabled(),true);
    await p.locator('[data-cmd="edge-prev"]').click();await p.locator('.reader-root[data-page="4"][data-ready="true"]').waitFor();await ready(p);
    await number(p,1);assert.equal(await p.locator('[data-cmd="edge-prev"]').isDisabled(),true);
    await p.locator('[data-cmd="thumbnails"]').click();assert.equal(await p.locator('.page-thumbnails').isVisible(),false);await fit(p,'thumbnails closed');await p.locator('[data-cmd="thumbnails"]').click();await fit(p,'thumbnails reopened');
    report.checks.push('Page thumbnails jump and highlight current page; side arrows flip and disable at boundaries; preview panel toggles');

    await number(p,3);const saved=await mark(p);let geometryError=0;
    for(const zoom of ['0.5','1.25','2.5']){await p.getByLabel('缩放',{exact:true}).selectOption(zoom);await redraw(p);for(let n=0;n<4;n++){const e=await p.locator('.reader-root').evaluate(r=>Math.max(...[[0,0],[1,1],[.2,.7]].flatMap(v=>r.probe.roundtrip(v).map((x,j)=>Math.abs(x-v[j])))));geometryError=Math.max(geometryError,e);assert.deepEqual(await p.locator('.reader-root').evaluate((r,id)=>r.probe.model.marks.find(m=>m.id===id).points,saved.id),saved.points);await p.locator('[data-cmd="rotate"]').click();await redraw(p);}}
    assert.ok(geometryError<1e-12);report.geometryError=geometryError;report.savedMark=saved;
    await p.getByLabel('缩放',{exact:true}).selectOption('fit-page');await redraw(p);await p.locator('[data-cmd="focus"]').click();await p.waitForFunction(()=>!!document.fullscreenElement);await fit(p,'fullscreen');
    await p.locator('.reader-root').screenshot({path:path.join(out,'reader-fullscreen.png')});await p.locator('[data-cmd="focus"]').click();await p.waitForFunction(()=>!document.fullscreenElement);await fit(p,'exit fullscreen');
    report.checks.push('Drawn annotation stays in canonical coordinates through 12 zoom/rotation combinations; fullscreen enters/exits with proportional fit');

    await p.getByLabel('缩放',{exact:true}).selectOption('2.5');await redraw(p);
    const oldScroll=await p.locator('.reader-root').evaluate(r=>{const s=r.querySelector('.page-scroll');s.scrollLeft=160;s.scrollTop=270;s.dispatchEvent(new Event('scroll'));const pdf=r.probe.model.pdf;pdf.__testGetPage=pdf.getPage.bind(pdf);pdf.getPage=async n=>{const page=await pdf.__testGetPage(n);if(n===4)await new Promise(resolve=>setTimeout(resolve,700));return page;};return {left:s.scrollLeft,top:s.scrollTop};});
    assert.ok(oldScroll.top>100);await p.locator('[data-cmd="edge-next"]').click();await p.locator('.reader-root[data-page="4"][data-ready="true"]').waitFor();await ready(p);await p.waitForTimeout(250);
    const resetScroll=await p.locator('.reader-root').evaluate(r=>{const s=r.querySelector('.page-scroll'),pdf=r.probe.model.pdf;pdf.getPage=pdf.__testGetPage;delete pdf.__testGetPage;return {left:s.scrollLeft,top:s.scrollTop};});
    assert.deepEqual(resetScroll,{left:0,top:0});report.delayedPage={oldScroll,resetScroll};report.checks.push('Delayed PDF rendering across save acknowledgement resets new-page scrolling instead of inheriting previous page offsets');

    await choose(p,setup.documents.long);await number(p,1);await redraw(p);
    assert.equal(await p.locator('.thumbnail').count(),300);
    const initial=await p.locator('.reader-root').evaluate(r=>({cache:r.probe.model.thumbCache.size,rendered:[...r.querySelectorAll('.thumbnail canvas')].filter(c=>c.width>1&&c.height>1).length}));
    assert.ok(initial.cache>0&&initial.cache<36,JSON.stringify(initial));assert.ok(initial.rendered<36,JSON.stringify(initial));
    for(const n of [30,60,90,120,150,180,210,240,270,300]){await p.locator(`.thumbnail[data-page="${n}"]`).scrollIntoViewIfNeeded();await p.waitForTimeout(350);const size=await p.locator('.reader-root').evaluate(r=>r.probe.model.thumbCache.size);assert.ok(size<=36,'bounded thumbnail cache');}
    const finalCache=await p.locator('.reader-root').evaluate(r=>({cache:r.probe.model.thumbCache.size,rendered:[...r.querySelectorAll('.thumbnail canvas')].filter(c=>c.width>1&&c.height>1).length}));
    assert.ok(finalCache.cache<=36);assert.ok(finalCache.rendered<=40,'offscreen thumbnail raster release');
    await p.locator('.thumbnail[data-page="300"]').click();await p.locator('.reader-root[data-page="300"][data-ready="true"]').waitFor();await ready(p);assert.equal(await p.locator('[data-cmd="edge-next"]').isDisabled(),true);
    report.thumbnails={initial,finalCache};report.checks.push('300-page thumbnails load lazily, stay within 36 cached rasters, release offscreen canvases and jump to last page');

    await choose(p,setup.documents.mixed);await number(p,3);await p.getByLabel('缩放',{exact:true}).selectOption('fit-page');await redraw(p);
    await p.locator('.reader-root').screenshot({path:path.join(out,'reader-desktop.png')});await number(p,1);await fit(p,'landscape screenshot');await p.locator('.reader-root').screenshot({path:path.join(out,'reader-landscape.png')});await number(p,3);
    await p.reload();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);await bookshelf(p);await choose(p,setup.documents.mixed);
    assert.equal(await p.locator('.reader-root').getAttribute('data-page'),'3');assert.deepEqual(await p.locator('.reader-root').evaluate((r,id)=>r.probe.model.marks.find(m=>m.id===id),saved.id),saved);
    report.checks.push('Reload restores saved reading page and exact annotation geometry');

    await p.setViewportSize({width:430,height:932});await p.reload();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);await bookshelf(p);await choose(p,setup.documents.mixed);await redraw(p);
    assert.equal(await p.locator('.page-thumbnails').isVisible(),false);await fit(p,'phone collapsed preview');
    const pageWidth=await p.evaluate(()=>({body:document.documentElement.scrollWidth,width:innerWidth}));assert.ok(pageWidth.body<=pageWidth.width+2,JSON.stringify(pageWidth));
    await p.locator('[data-cmd="thumbnails"]').click();assert.equal(await p.locator('.page-thumbnails').isVisible(),true);
    await p.locator('.thumbnail[data-page="2"]').click();await p.locator('.reader-root[data-page="2"][data-ready="true"]').waitFor();await ready(p);assert.equal(await p.locator('.page-thumbnails').isVisible(),false);await fit(p,'phone after thumbnail jump');
    await p.locator('.reader-root').screenshot({path:path.join(out,'reader-phone.png')});
    report.checks.push('Phone-sized browser has no horizontal overflow; previews start collapsed and close after page selection');

    for(const doc of Object.values(setup.documents))assert.equal(crypto.createHash('sha256').update(await fs.readFile(doc.source)).digest('hex'),doc.sha256);
    assert.equal(report.external.length,0);assert.equal(report.errors.length,0);assert.equal(report.consoleErrors.length,0);report.checks.push('Source PDFs unchanged, no external requests, browser exceptions or console errors');report.passed=true;
  }catch(error){report.passed=false;report.failure=error.stack;report.body=(await p.locator('body').innerText()).slice(-7000);report.readerState=await p.locator('.reader-root').evaluate(r=>({dataset:{...r.dataset},tool:r.probe?.model.tool,pending:r.probe?.model.pending,marks:r.probe?.model.marks})).catch(()=>null);await p.screenshot({path:path.join(out,'reader-navigation-failure.png')});throw error;}
  finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'reader-navigation-browser.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
})();

