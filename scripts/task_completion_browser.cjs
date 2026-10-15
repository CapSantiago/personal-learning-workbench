// End-to-end acceptance against a dedicated synthetic workspace on port 8505.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,rootArg]=process.argv.slice(2),root=path.resolve(rootArg);
const rel=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel),'Synthetic workspace required');
const {chromium}=require(path.join(modules,'playwright'));
const out=path.join(root,'evidence'),report={checks:[],external:[],errors:[]};
const idle=async p=>{await p.waitForTimeout(300);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');assert.equal(await p.getByTestId('stException').count(),0);};
const taskTitle='完成第二章课后习题';
const cards=p=>p.locator('[data-testid="stVerticalBlock"][class*="st-key-pending_task_"]');
async function archive(p){await p.getByRole('button',{name:'已完成任务',exact:true}).click();await p.getByRole('heading',{name:'已完成任务',exact:true}).waitFor();await idle(p);}
async function detail(p){const d=p.locator('details').filter({has:p.locator(':scope > summary').getByText(new RegExp(taskTitle))});await d.locator('summary').click();await d.getByRole('button',{name:'恢复待办',exact:true}).waitFor();await p.waitForTimeout(450);return d;}
async function home(p){await p.getByTestId('stSidebar').getByRole('button',{name:'今日学习',exact:true}).click();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',async r=>{if(new URL(r.request().url()).origin==='http://127.0.0.1:8505')await r.continue();else{report.external.push(r.request().url());await r.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).origin==='ws://127.0.0.1:8505')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.setDefaultTimeout(15000);p.on('pageerror',e=>report.errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:8505/');await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  if(await p.getByRole('button',{name:'完成',exact:true}).count()===1){await archive(p);const d=await detail(p);await d.getByRole('button',{name:'恢复待办',exact:true}).click();await idle(p);await home(p);}
  assert.equal(await p.getByRole('button',{name:'完成',exact:true}).count(),2);
  await p.screenshot({path:path.join(out,'completion-desktop.png'),fullPage:true});
  await cards(p).filter({hasText:taskTitle}).getByRole('button',{name:'完成',exact:true}).click();
  await p.getByText('任务已完成，已移入“已完成任务”存档。',{exact:true}).waitFor();await idle(p);
  assert.equal(await p.locator('.plw-task-title').filter({hasText:taskTitle}).count(),0);
  assert.equal(await p.getByRole('button',{name:'完成',exact:true}).count(),1);
  report.checks.push('Homepage completion immediately removes only selected pending task');
  await archive(p);let d=await detail(p);
  assert.match(await d.innerText(),/完成时间：.*北京时间/s);
  assert.match(await d.innerText(),/记录实验步骤与结果/);
  await p.screenshot({path:path.join(out,'completion-archive.png'),fullPage:true});
  await p.reload();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);await archive(p);d=await detail(p);
  report.checks.push('Completed archive preserves details and completion time across reload');
  await d.getByRole('button',{name:'恢复待办',exact:true}).click();await p.getByText('任务已恢复到待办列表。',{exact:true}).waitFor();await idle(p);
  assert.equal(await p.getByRole('button',{name:'恢复待办',exact:true}).count(),0);
  await home(p);assert.equal(await p.getByRole('button',{name:'完成',exact:true}).count(),2);
  report.checks.push('Reopen restores the task and removes it from completed archive');
  await p.setViewportSize({width:390,height:844});await idle(p);
  const collapse=p.getByTestId('stSidebarCollapseButton').getByRole('button');
  if(await p.getByTestId('stSidebar').getAttribute('aria-expanded')==='true')await collapse.click();
  await cards(p).filter({hasText:taskTitle}).scrollIntoViewIfNeeded();
  assert.ok(await cards(p).filter({hasText:taskTitle}).getByRole('button',{name:'完成',exact:true}).isVisible());
  const overflow=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
  assert.equal(overflow,false);
  await p.screenshot({path:path.join(out,'completion-mobile.png'),fullPage:true});
  await cards(p).filter({hasText:taskTitle}).getByRole('button',{name:'完成',exact:true}).click();
  await p.getByText('任务已完成，已移入“已完成任务”存档。',{exact:true}).waitFor();await idle(p);await archive(p);
  d=await detail(p);assert.ok(await d.getByRole('button',{name:'恢复待办',exact:true}).isVisible());
  report.checks.push('390px mobile layout has no horizontal overflow; complete and archive are usable');
  assert.deepEqual(report.external,[]);assert.deepEqual(report.errors,[]);report.passed=true;
 }catch(e){report.failure=e.stack;await p.screenshot({path:path.join(out,'completion-failure.png'),fullPage:true});throw e;}
 finally{await fs.writeFile(path.join(out,'completion-browser.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1;});
