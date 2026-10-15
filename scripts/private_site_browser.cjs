// Synthetic-only private-site acceptance. No real credentials or learning files.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,rootArg,originArg]=process.argv.slice(2),root=path.resolve(rootArg),base=originArg||'http://127.0.0.1:8505';
assert.ok(['http://127.0.0.1:8505','https://127.0.0.1:8506'].includes(base));
const rel=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel));
const {chromium}=require(path.join(modules,'playwright'));
const out=path.join(root,'evidence'),report={checks:[],external:[],errors:[]};
const idle=async p=>{await p.waitForTimeout(350);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');assert.equal(await p.getByTestId('stException').count(),0);};
async function expand(p,name){const d=p.locator('details').filter({has:p.locator(':scope > summary').getByText(name,{exact:true})}).first();if(!await d.evaluate(e=>e.open))await d.locator(':scope > summary').click();await p.waitForTimeout(400);}
async function login(p){await p.goto(base);await p.getByLabel('账号',{exact:true}).fill('student');await p.getByLabel('密码',{exact:true}).fill('Synthetic-login-only-2026');await p.getByRole('button',{name:'登录',exact:true}).click();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true,ignoreHTTPSErrors:true});
 await context.route('**/*',async r=>{const u=new URL(r.request().url());if(u.origin===base||u.protocol==='file:')await r.continue();else{report.external.push(u.origin);await r.abort();}});
 const liveSockets=new Set();
 const p=await context.newPage();p.setDefaultTimeout(20000);p.on('pageerror',e=>report.errors.push(e.message));
 p.on('websocket',ws=>{if(new URL(ws.url()).origin!==base.replace('http','ws'))report.external.push(ws.url());liveSockets.add(ws);ws.on('close',()=>liveSockets.delete(ws));});
 try{
  await p.goto(base);await p.getByRole('button',{name:'登录',exact:true}).waitFor();await p.screenshot({path:path.join(out,'private-login-desktop.png')});
  for(const resource of ['/_stcore/upload_file/a/b','/plw-reader/copied/download/unknown','/media/private.pdf']){
   assert.equal((await context.request.get(base+resource)).status(),401);
  }
  report.checks.push('Anonymous requests cannot read uploads, download routes or media');
  await login(p);
  const authCookie=(await context.cookies()).find(c=>c.name==='plw_private_session');
  assert.equal(authCookie.secure,base.startsWith('https:'));assert.equal(authCookie.httpOnly,true);assert.equal(authCookie.sameSite,'Strict');
  const side=p.getByTestId('stSidebar');await side.getByRole('button',{name:/课程书架/}).click();await idle(p);
  await side.getByRole('button',{name:'机器人学',exact:true}).click();await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);
  await expand(p,'下载与离线阅读');
  const link=p.getByRole('link',{name:'下载 PDF 到设备',exact:true}),url=await link.getAttribute('href');
  const response=await context.request.get(base+url);assert.equal(response.status(),200);assert.match(response.headers()['content-disposition'],/attachment/);
  assert.deepEqual(await response.body(),await fs.readFile(path.join(root,'source.pdf')));
  const [download]=await Promise.all([p.waitForEvent('download'),link.click()]);
  assert.equal(download.suggestedFilename(),'第一讲 中文课件.pdf');await download.saveAs(path.join(out,'offline-courseware.pdf'));
  assert.deepEqual(await fs.readFile(path.join(out,'offline-courseware.pdf')),await fs.readFile(path.join(root,'source.pdf')));
  const anonymous=await browser.newContext({ignoreHTTPSErrors:true});assert.equal((await anonymous.request.get(base+url)).status(),401);await anonymous.close();
  report.checks.push('Authenticated native download preserves PDF bytes and Chinese filename; copied link rejects anonymous access');
  await p.screenshot({path:path.join(out,'private-download-desktop.png'),fullPage:true});
  await expand(p,'生成阅读副本 / 添加新版本');
  assert.equal(await p.getByLabel('使用已导出的 PDF 路径（可选）',{exact:true}).count(),0);
  await p.getByTestId('stFileUploader').filter({hasText:'选择已导出的 PDF'}).locator('input[type=file]').setInputFiles(path.join(root,'source.pdf'));
  await idle(p);await p.getByText('确认保存 PDF 阅读副本',{exact:true}).click();
  await p.getByRole('button',{name:'生成阅读副本',exact:true}).click();await p.getByText('阅读副本已保存，可以开始阅读和标记。',{exact:true}).waitFor();await idle(p);
  report.checks.push('Reading version can be supplied through browser upload without a server path');
  await p.setViewportSize({width:820,height:1180});await idle(p);
  const collapse=p.getByTestId('stSidebarCollapseButton').getByRole('button');
  if(await collapse.count()&&await collapse.isVisible()&&await side.getAttribute('aria-expanded')==='true')await collapse.click();
  await expand(p,'下载与离线阅读');assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await p.getByRole('link',{name:'下载 PDF 到设备',exact:true}).scrollIntoViewIfNeeded();
  await p.screenshot({path:path.join(out,'private-download-tablet.png'),fullPage:true});
  const sockets=[...liveSockets];assert.ok(sockets.length>0,'An authenticated Streamlit WebSocket must be open');
  // Logout in another tab must revoke cookies and the existing Streamlit socket.
  const logout=await context.newPage();await logout.goto(base+'/plw-auth/logout');await logout.getByRole('button',{name:'确认退出',exact:true}).click();await logout.getByRole('button',{name:'登录',exact:true}).waitFor();
  assert.equal((await context.request.get(base+url)).status(),401);
  await p.waitForTimeout(1000);assert.ok(sockets.every(ws=>ws.isClosed()));
  report.checks.push('Logout revokes download access and closes open WebSocket connections');
  await logout.setViewportSize({width:390,height:844});await logout.screenshot({path:path.join(out,'private-login-mobile.png')});
  await context.setOffline(true);
  const offline=await context.newPage();await offline.goto('file:///'+path.join(out,'offline-courseware.pdf').replaceAll('\\','/'));
  await offline.waitForTimeout(900);await offline.screenshot({path:path.join(out,'offline-pdf.png')});
  report.offlinePageUrl=offline.url();report.checks.push('Saved PDF opens from device file with browser network disabled');
  assert.deepEqual(report.external,[]);assert.deepEqual(report.errors,[]);report.passed=true;
 }catch(e){report.failure=e.stack;await p.screenshot({path:path.join(out,'private-site-failure.png'),fullPage:true});throw e;}
 finally{report.origin=base;await fs.writeFile(path.join(out,base.startsWith('https:')?'private-site-https-browser.json':'private-site-browser.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;});
