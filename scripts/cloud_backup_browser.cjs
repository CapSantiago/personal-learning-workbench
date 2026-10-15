// Synthetic-only acceptance for the new complete-backup browser download.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,rootArg]=process.argv.slice(2),root=path.resolve(rootArg),base='http://127.0.0.1:8505';
const relative=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative));
const {chromium}=require(path.join(modules,'playwright'));
const report={checks:[],errors:[],external:[]},out=path.join(root,'evidence');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await browser.newContext({viewport:{width:820,height:1180},acceptDownloads:true});
 await context.route('**/*',async route=>{const url=new URL(route.request().url());if(url.origin===base)await route.continue();else{report.external.push(url.origin);await route.abort();}});
 const page=await context.newPage();page.setDefaultTimeout(25000);page.on('pageerror',e=>report.errors.push(e.message));
 try{
  assert.equal((await context.request.get(base+'/plw-health')).status(),200);
  await page.goto(base);await page.getByLabel('账号',{exact:true}).fill('student');await page.getByLabel('密码',{exact:true}).fill('Synthetic-login-only-2026');await page.getByRole('button',{name:'登录',exact:true}).click();
  await page.getByRole('heading',{name:'今日学习',exact:true}).waitFor();
  if(!await page.getByTestId('stSidebar').isVisible())await page.getByTestId('stExpandSidebarButton').click();
  const sidebar=page.getByTestId('stSidebar');
  const settings=sidebar.locator('details').filter({hasText:'课程与设置'}).first();
  if(!await settings.evaluate(e=>e.open))await settings.locator('summary').click();
  await sidebar.getByRole('button',{name:'数据与备份',exact:true}).click();
  await page.getByRole('button',{name:'生成完整备份包',exact:true}).click();
  const link=page.getByRole('link',{name:'下载完整备份包',exact:true});await link.waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  const url=await link.getAttribute('href'),response=await context.request.get(base+url);assert.equal(response.status(),200);
  const [download]=await Promise.all([page.waitForEvent('download'),link.click()]);
  assert.match(download.suggestedFilename(),/^PLW-.*\.zip$/);
  const saved=path.join(out,'browser-complete-backup.zip');await download.saveAs(saved);
  assert.deepEqual(await fs.readFile(saved),await response.body());
  const anon=await browser.newContext();assert.equal((await anon.request.get(base+url)).status(),401);await anon.close();
  report.archive=saved;report.checks.push('Tablet-sized UI generates and downloads complete ZIP; anonymous copied link is denied');
  await page.screenshot({path:path.join(out,'cloud-backup-tablet.png'),fullPage:true});
  assert.deepEqual(report.external,[]);assert.deepEqual(report.errors,[]);report.passed=true;
 }catch(error){report.failure=error.stack;await page.screenshot({path:path.join(out,'cloud-backup-failure.png'),fullPage:true});throw error;}
 finally{await fs.writeFile(path.join(out,'cloud-backup-browser.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify(report));
})().catch(error=>{console.error(error);process.exitCode=1;});
