const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto'),cp=require('node:child_process');
const [modules,root]=process.argv.slice(2),{chromium}=require(path.join(modules,'playwright'));
const project=path.resolve(__dirname,'..'),evidence=path.join(root,'evidence');
const report={started:new Date().toISOString(),checks:[],external:[],errors:[]};
const safe=u=>{try{return new URL(u).hostname==='127.0.0.1'}catch{return false}};
const idle=async p=>{await p.waitForTimeout(250);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor({timeout:120000});await idle(p);assert.equal(await p.locator('[data-testid="stException"]').count(),0);};
const nav=async(p,label)=>{const sidebar=p.locator('[data-testid="stSidebar"]'),button=sidebar.getByRole('button',{name:label,exact:true});if(!(await button.isVisible()))await sidebar.getByText('课程与设置',{exact:true}).click();await button.click();await idle(p);};
const select=async(p,label,value)=>{await p.getByLabel(label,{exact:true}).click();await p.getByLabel(label,{exact:true}).fill(value);await p.getByRole('option',{name:value,exact:true}).click();await idle(p);};
async function importFile(p,name){
  let exists=false;if(await p.getByLabel('选择课件',{exact:true}).count()){await p.getByLabel('选择课件',{exact:true}).click();const option=p.getByRole('option',{name,exact:true});if(await option.count()){await option.first().click();await idle(p);exists=true;}else await p.keyboard.press('Escape');}
  const exp=p.getByText('添加本课程资料',{exact:true});
  if(!exists){
  if(!(await p.getByLabel('文件绝对路径',{exact:true}).isVisible()))await exp.click();
  await p.getByLabel('文件绝对路径',{exact:true}).fill(path.join(root,'sources',name));
  await p.getByRole('button',{name:'添加资料',exact:true}).click();await idle(p);
  }
  if(await p.getByLabel('选择课件',{exact:true}).count())await select(p,'选择课件',name);
  if(await p.locator('.reader-root').count()){await ready(p);return;}
  if(!(await p.getByText('确认生成并保存本地 PDF 阅读副本',{exact:true}).isVisible()))await p.getByText('生成阅读副本 / 添加新版本',{exact:true}).click();
  await p.getByText('确认生成并保存本地 PDF 阅读副本',{exact:true}).click();
  await p.getByRole('button',{name:'生成阅读副本',exact:true}).click();await ready(p);
}
(async()=>{
 await fs.mkdir(evidence,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await browser.newContext({viewport:{width:1440,height:1100}});
 await context.route('**/*',async r=>{if(safe(r.request().url()))await r.continue();else{report.external.push(r.request().url());await r.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(safe(ws.url()))ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.on('pageerror',e=>report.errors.push(e.message));p.setDefaultTimeout(30000);
 try{
  await p.goto('http://127.0.0.1:8505');await p.getByRole('heading',{name:/^(今日学习|欢迎使用 PLW)$/}).waitFor();await idle(p);
  if(await p.getByText('确认在上述学习数据目录创建新的空学习库',{exact:true}).count()){
   await p.getByText('确认在上述学习数据目录创建新的空学习库',{exact:true}).click();
   await p.getByRole('button',{name:'创建学习库并开始',exact:true}).click();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  }
  const seed=cp.spawnSync(path.join(project,'.venv/Scripts/python.exe'),['-X','utf8','-B',path.join(project,'scripts/framework_acceptance_seed.py'),root],{encoding:'utf8'});assert.equal(seed.status,0,seed.stderr);
  await p.reload();await idle(p);report.checks.push('explicit first-use in synthetic workspace');
  await nav(p,'课程书架');
  await importFile(p,'原生 PDF 中文课件.pdf');assert.match(await p.locator('.reader-root').getAttribute('data-text'),/控制原理/);
  const base=Number(await p.locator('.reader-root').getAttribute('data-marks'));
  for(const type of ['rectangle','highlight','ink']){
   const before=Number(await p.locator('.reader-root').getAttribute('data-marks'));
   await p.locator(`[data-cmd="${type}"]`).click();await p.locator('canvas.marks').scrollIntoViewIfNeeded();const b=await p.locator('canvas.marks').boundingBox();
   await p.mouse.move(b.x+90,b.y+100);await p.mouse.down();await p.mouse.move(b.x+260,b.y+180,{steps:12});await p.mouse.up();
   await p.locator(`.reader-root[data-marks="${before+1}"]`).waitFor();await ready(p);
  }
  await p.locator('[data-cmd="undo"]').click();await p.locator(`.reader-root[data-marks="${base+2}"]`).waitFor();await ready(p);
  await p.locator('[data-cmd="redo"]').click();await p.locator(`.reader-root[data-marks="${base+3}"]`).waitFor();await ready(p);
  await p.getByLabel('跳转页码',{exact:true}).fill('2');await p.locator('[data-cmd="jump"]').click();await ready(p);
  if(!(await p.getByLabel('标记内容（可写公式和 Markdown）',{exact:true}).isVisible()))await p.getByText('书签与批注',{exact:true}).click();
  await p.getByLabel('标记内容（可写公式和 Markdown）',{exact:true}).fill('控制系统：复习 $G(s)$');
  await p.getByRole('button',{name:'保存标记',exact:true}).click();await ready(p);
  await p.reload();await idle(p);await nav(p,'课程书架');await ready(p);assert.equal(await p.locator('.reader-root').getAttribute('data-page'),'2');assert.equal(await p.locator('.reader-root').getAttribute('data-marks'),String(base+3));
  await p.screenshot({path:path.join(evidence,'reader.png'),fullPage:true});report.checks.push('PDF import, all graphic tools, undo/redo, bookmark, page persistence');
  await importFile(p,'宽屏 合成课件.pptx');assert.match(await p.locator('.reader-root').getAttribute('data-text'),/控制原理/);
  await p.screenshot({path:path.join(evidence,'pptx-reader.png'),fullPage:true});report.checks.push('PPTX copy, live PowerPoint conversion and local reader');
  await importFile(p,'旧格式 合成课件.ppt');assert.match(await p.locator('.reader-root').getAttribute('data-text'),/控制原理/);report.checks.push('legacy PPT conversion and local reader');
  await nav(p,'任务管理');if(!(await p.getByLabel('任务标题',{exact:true}).isVisible()))await p.getByText('添加新任务',{exact:true}).click();await p.getByLabel('任务标题',{exact:true}).fill('合成验收：闭环复习');await p.getByRole('button',{name:'保存任务',exact:true}).click();await idle(p);
  await nav(p,'章节与知识点');await p.getByLabel('章节名称',{exact:true}).fill('第一章 闭环控制');await p.getByRole('button',{name:'保存章节',exact:true}).click();await idle(p);
  await p.getByLabel('知识点名称',{exact:true}).fill('稳定性判据');await p.getByRole('button',{name:'保存知识点',exact:true}).click();await idle(p);
  await nav(p,'笔记');await p.getByLabel('笔记标题',{exact:true}).fill('控制理论公式');await p.getByLabel('Markdown 正文',{exact:true}).fill('# 反馈\n\n行内 $x^2$\n\n$$G(s)=\\frac{1}{s+1}$$');await p.getByRole('button',{name:'保存笔记',exact:true}).click();await idle(p);
  await select(p,'选择笔记','控制理论公式');await p.getByRole('tab',{name:'阅读预览',exact:true}).click();await p.locator('.katex').filter({visible:true}).first().waitFor();await p.screenshot({path:path.join(evidence,'notes.png'),fullPage:true});report.checks.push('task, chapter, knowledge point and Markdown/LaTeX rendering');
  await nav(p,'数据与备份');await p.getByRole('button',{name:'创建完整备份',exact:true}).click();await p.getByText('完整备份已验证。外部引用只备份索引。',{exact:true}).waitFor();await idle(p);report.checks.push('complete backup created and verified through UI');
  assert.equal(await p.locator('[data-testid="stException"]').count(),0);assert.equal(report.external.length,0);assert.equal(report.errors.length,0);
  report.passed=true;
 }catch(e){report.passed=false;report.failure=e.stack;report.body=(await p.locator('body').innerText()).slice(-9000);await p.screenshot({path:path.join(evidence,'failure.png'),fullPage:true});throw e;}
 finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(evidence,'framework-browser.json'),JSON.stringify(report,null,2));await browser.close();console.log(JSON.stringify(report,null,2));}
})();
