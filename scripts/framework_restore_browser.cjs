const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,root,mode='restore']=process.argv.slice(2),{chromium}=require(path.join(modules,'playwright'));
const out=path.join(root,'evidence'),report={started:new Date().toISOString(),mode,external:[],errors:[]};
const idle=async p=>{await p.waitForTimeout(250);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');};
const nav=async(p,label)=>{const sidebar=p.locator('[data-testid="stSidebar"]'),button=sidebar.getByRole('button',{name:label,exact:true});if(!(await button.isVisible()))await sidebar.getByText('课程与设置',{exact:true}).click();await button.click();await idle(p);};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);};
async function readState(p){await nav(p,'课程书架');await ready(p);return await p.locator('.reader-root').evaluate(r=>({doc:r.dataset.doc,page:r.dataset.page,marks:r.dataset.marks,base:r.probe.model.base}));}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1100}});
 await context.route('**/*',async route=>{if(new URL(route.request().url()).hostname==='127.0.0.1')await route.continue();else{report.external.push(route.request().url());await route.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).hostname==='127.0.0.1')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.on('pageerror',e=>report.errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:8505');await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  const before=await readState(p);assert.ok(Number(before.marks)>=3);assert.equal(before.page,'2');
  if(mode==='restore'){
   await nav(p,'数据与备份');await p.getByRole('button',{name:'创建完整备份',exact:true}).click();await p.getByText('完整备份已验证。外部引用只备份索引。',{exact:true}).waitFor();await idle(p);
   report.oldDataset=(await p.getByText(/^当前数据集：/).innerText()).split('：')[1].trim();
   await p.getByRole('button',{name:'验证并预览备份',exact:true}).click();await idle(p);
   await p.getByLabel('输入当前数据集 ID 确认恢复',{exact:true}).fill(report.oldDataset);
   await p.getByRole('button',{name:'恢复并切换数据集',exact:true}).click();await idle(p);
   const restored=await readState(p);for(const key of ['doc','page','marks'])assert.equal(restored[key],before[key]);
   await p.locator('.reader-root').screenshot({path:path.join(out,'restored-reader.png')});
   await nav(p,'笔记');await p.getByLabel('选择笔记',{exact:true}).click();await p.getByLabel('选择笔记',{exact:true}).fill('控制理论公式');await p.getByRole('option',{name:'控制理论公式',exact:true}).click();await idle(p);
   await p.getByRole('tab',{name:'阅读预览',exact:true}).click();
   await p.locator('.katex').filter({visible:true}).last().screenshot({path:path.join(out,'restored-formula.png')});
   await nav(p,'数据与备份');report.restoredDataset=(await p.getByText(/^当前数据集：/).innerText()).split('：')[1].trim();assert.notEqual(report.oldDataset,report.restoredDataset);
   await p.getByLabel('输入当前数据集 ID 确认维护操作',{exact:true}).fill(report.restoredDataset);
   await p.getByRole('button',{name:'保存当前副本并回滚',exact:true}).click();await idle(p);
   const rolled=await readState(p);for(const key of ['doc','page','marks'])assert.equal(rolled[key],before[key]);
   await fs.writeFile(path.join(out,'before-restart.json'),JSON.stringify(rolled));report.checks=['restore into new dataset','restored PDF and graphics visible','restored LaTeX note visible','rollback preserves reading state'];
  }else{
   const expected=JSON.parse(await fs.readFile(path.join(out,'before-restart.json'),'utf8'));
   for(const key of ['doc','page','marks'])assert.equal(before[key],expected[key]);
   await p.locator('.reader-root').screenshot({path:path.join(out,'restarted-reader.png')});report.checks=['real server restart restores same PDF edition, page and graphics'];
  }
  assert.equal(report.external.length,0);assert.equal(report.errors.length,0);report.passed=true;
 }catch(e){report.passed=false;report.failure=e.stack;report.body=(await p.locator('body').innerText()).slice(-9000);throw e;}
 finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'framework-'+mode+'.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
})();
