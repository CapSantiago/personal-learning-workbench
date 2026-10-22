const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
const folder=process.argv[2],cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8')),report={checks:[],timings:[],pageerrors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
try{
const context=await browser.newContext({viewport:{width:1500,height:1050}});await context.addCookies([{name:cfg.cookie_name,value:cfg.cookie,url:cfg.origin}]);
const p=await context.newPage();p.setDefaultTimeout(30000);p.on('pageerror',e=>report.pageerrors.push(e.message));
await context.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());
await p.goto(cfg.origin);await p.locator('.reader-root[data-ready="true"][data-page="1"]').waitFor();
const stats=()=>p.evaluate(async()=>await(await fetch('/fixture/stats')).json());
const mode=value=>p.evaluate(async value=>await fetch('/fixture/stats',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}),value);
const settled=()=>p.waitForFunction(()=>{const m=document.querySelector('.reader-root').probe?.model;return m&&!m.pending&&m.queuedPage===null&&!m.saveError;});
async function go(n){const t=performance.now();await p.getByLabel('跳转页码',{exact:true}).fill(String(n));await p.locator('[data-cmd="jump"]').click();await p.locator(`.reader-root[data-ready="true"][data-page="${n}"]`).waitFor();const value=await p.locator('.reader-root').evaluate(r=>({ms:+r.dataset.renderMs,cacheHits:+r.dataset.pageCacheHits,pixels:r.probe.canvas.width*r.probe.canvas.height}));report.timings.push({page:n,wall_ms:Math.round(performance.now()-t),...value});assert.ok(value.pixels>100000);}
await p.waitForFunction(()=>document.querySelector('.reader-root').probe.model.pageRasters.size>=3);
await go(2);await p.waitForTimeout(450);assert.equal(await p.locator('[data-cmd="next"]').isDisabled(),false);assert.match(await p.locator('.read-status').textContent(),/后台保存/);
await go(3);await go(4);await go(5);assert.equal(await p.locator('[data-cmd="next"]').isDisabled(),false);await settled();
const firstStats=await stats();assert.deepEqual(firstStats.action_requests.map(a=>a.page),[2,5]);report.checks.push('3-second delayed save ACK permits pages 2 -> 3 -> 4 -> 5, coalesces final position and causes zero component triggers');
await go(17);await settled();await p.locator('[data-cmd="rectangle"]').click();
const points=await p.locator('.reader-root').evaluate(r=>{const b=r.probe.overlay.getBoundingClientRect();return [[.2,.2],[.4,.4]].map(v=>{const x=r.probe.screen(v);return{x:b.left+x[0],y:b.top+x[1]};});});
await p.mouse.move(points[0].x,points[0].y);await p.mouse.down();await p.mouse.move(points[1].x,points[1].y,{steps:3});await p.mouse.up();
await go(18);await settled();let state=await p.evaluate(async()=>await(await fetch('/fixture/config/0')).json());assert.equal(state.state.marks.length,1);assert.equal(state.state.marks[0].page,17);assert.equal(state.state.page,18);
assert.equal(await p.locator('.reader-root').getAttribute('data-error'),null);report.checks.push('Delayed annotation save retains page-17 coordinates while navigation reaches page 18');
await mode({fail:true,delay:.2});await go(19);await p.waitForFunction(()=>!!document.querySelector('.reader-root').probe.model.saveError);await go(20);assert.equal(await p.locator('[data-cmd="next"]').isDisabled(),false);await mode({fail:false});await p.locator('[data-cmd="retry"]').click();await settled();
const retryStats=await stats(),attempts=retryStats.action_requests.filter(a=>a.page===19);assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1]);state=await p.evaluate(async()=>await(await fetch('/fixture/config/0')).json());assert.equal(state.state.page,20);report.checks.push('Save failure preserves identical id for retry; navigation continues and latest page 20 eventually persists');
await mode({delay:0});const beforeReload=(await stats()).pdf_requests;await p.reload();await p.locator('.reader-root[data-ready="true"][data-page="20"]').waitFor();assert.equal((await stats()).pdf_requests,beforeReload);assert.equal(await p.locator('.reader-root').evaluate(r=>r.probe.model.marks.length),1);report.checks.push('Reload restores saved page/mark from server and reuses IndexedDB without another PDF download');
await p.evaluate(()=>mountReader(1));await p.locator('.reader-root[data-ready="true"][data-page="1"]').waitFor();const beforeReturn=(await stats()).pdf_requests;await p.evaluate(()=>mountReader(0));await p.locator('.reader-root[data-ready="true"][data-page="20"]').waitFor();assert.equal((await stats()).pdf_requests,beforeReturn);report.checks.push('Real 54-page -> 35-page -> 54-page document switch reuses local PDF and raster');
await p.waitForFunction(()=>document.querySelector('.reader-root').probe.model.pageRasters.size>=3);await go(21);await p.waitForTimeout(250);await go(20);await settled();
await p.locator('.reader-root').screenshot({path:path.join(folder,'reader-desktop.png')});
await p.setViewportSize({width:820,height:1050});await p.waitForTimeout(600);await go(21);await settled();await p.locator('[data-cmd="rotate"]').click();await p.waitForTimeout(450);await p.locator('.reader-root[data-ready="true"]').waitFor();await p.locator('.reader-root').screenshot({path:path.join(folder,'reader-tablet-size.png')});
report.checks.push('Tablet-sized viewport and rotation render correctly; this is not physical iPad acceptance');assert.deepEqual(report.pageerrors,[]);
report.passed=true;report.final_stats=await stats();await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
