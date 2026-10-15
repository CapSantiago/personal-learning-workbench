/* Synthetic M2 acceptance: existing bundled Playwright, loopback-only routes. */
const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {chromium}=require(path.join(process.argv[2],'playwright'));
const root=path.resolve(__dirname,'..'),base=path.join(root,'.sandbox'),work=path.join(base,'m2');
const run=crypto.randomUUID().slice(0,8),semester=`M2 合成学期 ${run}`,course=`M2 控制原理 ${run}`;
const managed=`M2 托管资料 ${run}`,reference=`M2 引用资料 ${run}`;
const report={startedAt:new Date().toISOString(),run,semester,course,managed,reference,checks:[],externalRequests:[],pageErrors:[],consoleErrors:[]};
const settle=p=>p.waitForFunction(()=>{
  const labels=Array.from(document.querySelectorAll('[data-testid="stForm"] button[kind$="FormSubmit"]')).map(x=>x.textContent.trim());
  return document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning'&&!document.querySelector('[data-stale="true"]')&&new Set(labels).size===labels.length;
});
const form=(p,label)=>p.getByTestId('stForm').filter({has:p.getByRole('button',{name:label,exact:true,includeHidden:true})});
const nav=async(p,label)=>{await p.getByTestId('stSidebar').getByText(label,{exact:true}).click();await p.getByRole('heading',{name:label,exact:true}).waitFor();await settle(p);};
const success=async(p,text)=>{await p.getByText(text,{exact:true}).waitFor();await settle(p);};
const choose=async(scope,label,text,prefix=false)=>{
  const c=scope.getByLabel(label,{exact:true});const value=await c.inputValue();
  if(prefix?value.startsWith(text):value===text)return;
  await c.fill(text);await c.press('ArrowDown');
  const escaped=text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const option=scope.page().getByRole('option',{name:prefix?new RegExp('^'+escaped):text,exact:!prefix}).first();
  await option.waitFor();await option.click();
};
const sha=async p=>crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const pointer=async()=>JSON.parse(await fs.readFile(path.join(work,'control','active.json'),'utf8'));
const courseReady=async p=>{await p.waitForFunction(name=>Array.from(document.querySelectorAll('[data-testid="stForm"]')).some(f=>Array.from(f.querySelectorAll('button')).some(b=>b.textContent.trim()==='保存课程修改')&&f.querySelector('input[aria-label="课程名称"]')?.value===name),course);await settle(p);};
const local=u=>['127.0.0.1','localhost','[::1]'].includes(new URL(u).hostname);
(async()=>{
  const context=await chromium.launchPersistentContext(path.join(base,'browser-profiles',crypto.randomUUID()),{channel:'msedge',headless:true,viewport:{width:1440,height:1500},args:['--disable-background-networking','--disable-component-update','--no-first-run']});
  let p;
  try{
    await context.route('**/*',async r=>{if(local(r.request().url()))await r.continue();else{report.externalRequests.push(r.request().url());await r.abort();}});
    if(context.routeWebSocket)await context.routeWebSocket('**/*',ws=>{if(local(ws.url()))ws.connectToServer();else{report.externalRequests.push(ws.url());ws.close();}});
    p=await context.newPage();p.on('pageerror',e=>report.pageErrors.push(e.message));p.on('console',m=>{if(m.type()==='error')report.consoleErrors.push(m.text());});
    await p.goto('http://127.0.0.1:8501');await p.getByRole('heading',{name:'Personal Learning Workbench',exact:true}).waitFor();await settle(p);
    const init=p.getByRole('button',{name:'创建 M2 合成工作区',exact:true});
    if(await init.count()){await init.click();await success(p,'M2 合成工作区已创建，请添加验收用学期和课程。');report.checks.push('explicit synthetic workspace initialization');}
    const m1Hash=await sha(path.join(base,'m1','plw.sqlite3'));
    await nav(p,'学期管理');let f=form(p,'创建学期');await f.getByLabel('学期名称',{exact:true}).fill(semester);await f.getByRole('button',{name:'创建学期',exact:true}).click();await success(p,'学期已保存。相同表单再次提交不会重复创建。');
    await nav(p,'课程工作台');f=form(p,'创建课程');await choose(f,'所属学期',semester);await f.getByLabel('课程名称',{exact:true}).fill(course);await f.getByLabel('教师',{exact:true}).fill('备份时教师');await f.getByRole('button',{name:'创建课程',exact:true}).click();await success(p,'课程已保存。相同表单再次提交不会重复创建。');
    await nav(p,'资料管理');await p.getByRole('button',{name:'生成合成来源样例',exact:true}).click();await success(p,'合成来源样例已就绪，已有文件不会覆盖。');
    const source=path.join(work,'sources','合成 控制原理.txt'),external=path.join(work,'sources','合成 外部参考.txt');
    const originals=await Promise.all([source,external].map(async file=>({file,sha256:await sha(file),mtimeNs:String((await fs.stat(file,{bigint:true})).mtimeNs)})));
    f=form(p,'添加资料');await choose(f,'资料所属课程',course,true);await f.getByLabel('资料名称（留空使用文件名）',{exact:true}).fill(managed);await f.getByRole('button',{name:'添加资料',exact:true}).click();await success(p,`资料已保存：${managed}。相同请求再次提交不会重复添加。`);
    await f.getByRole('button',{name:'添加资料',exact:true}).click();await success(p,`资料已保存：${managed}。相同请求再次提交不会重复添加。`);
    await p.getByRole('button',{name:'继续添加另一份资料',exact:true}).click();
    await p.waitForFunction(()=>Array.from(document.querySelectorAll('input[aria-label="资料名称（留空使用文件名）"]')).some(x=>x.value===''));await settle(p);
    f=form(p,'添加资料');await choose(f,'资料所属课程',course,true);await choose(f,'存储方式','外部引用（只保存路径）');await f.getByLabel('来源文件路径',{exact:true}).fill(external);await f.getByLabel('资料名称（留空使用文件名）',{exact:true}).fill(reference);assert.equal(await f.getByLabel('来源文件路径',{exact:true}).inputValue(),external);await f.getByRole('button',{name:'添加资料',exact:true}).click();await success(p,`资料已保存：${reference}。相同请求再次提交不会重复添加。`);
    await choose({getByLabel:(...a)=>p.getByLabel(...a),page:()=>p},'查看资料',managed,true);
    await p.getByTestId('stText').filter({hasText:managed+' · '}).waitFor();await settle(p);await p.getByRole('button',{name:'隐藏资料记录（保留文件）',exact:true}).click();await success(p,'资料索引显示状态已更新，磁盘文件未删除。');
    report.checks.push('managed copy + replay, external reference, logical hide via real browser');
    await nav(p,'数据与备份');await p.getByRole('button',{name:'创建完整备份',exact:true}).click();await success(p,'完整备份已验证。外部引用只备份索引。');
    const backup=await p.getByLabel('备份目录路径',{exact:true}).inputValue();report.backupPath=backup;
    const manifest=JSON.parse(await fs.readFile(path.join(backup,'manifest.json'),'utf8'));
    assert.equal(manifest.complete,true);assert.ok(manifest.external.some(x=>x.included===false&&x.reference_path===external));report.checks.push('complete backup published with explicit excluded external file report and selected source path');
    const oldId=(await pointer()).dataset_id;report.oldDatasetId=oldId;
    await nav(p,'课程工作台');await p.getByLabel('搜索课程',{exact:true}).fill(course);await p.getByLabel('搜索课程',{exact:true}).press('Enter');await courseReady(p);
    f=form(p,'保存课程修改');await f.getByLabel('教师',{exact:true}).fill('恢复前修改教师');await f.getByRole('button',{name:'保存课程修改',exact:true}).click();await success(p,'课程修改已保存。');
    await nav(p,'数据与备份');await p.getByLabel('备份目录路径',{exact:true}).fill(backup);await p.getByRole('button',{name:'验证并预览备份',exact:true}).click();await p.getByLabel('输入当前数据集 ID 确认恢复',{exact:true}).waitFor();await settle(p);
    f=form(p,'恢复并切换数据集');await f.getByLabel('输入当前数据集 ID 确认恢复',{exact:true}).fill('incorrect-confirmation');await f.getByRole('button',{name:'恢复并切换数据集',exact:true}).click();await p.getByTestId('stAlert').filter({hasText:'确认值必须'}).waitFor();assert.equal((await pointer()).dataset_id,oldId);report.checks.push('incorrect restore confirmation refused without switching');
    await f.getByLabel('输入当前数据集 ID 确认恢复',{exact:true}).fill(oldId);await f.getByRole('button',{name:'恢复并切换数据集',exact:true}).click();await success(p,'恢复验证完成，已切换到新数据集；旧数据及恢复前副本保留。');
    const newId=(await pointer()).dataset_id;assert.notEqual(newId,oldId);report.newDatasetId=newId;await fs.access(path.join(work,'datasets',oldId,'plw.sqlite3'));
    await nav(p,'课程工作台');await p.getByLabel('搜索课程',{exact:true}).fill(course);await p.getByLabel('搜索课程',{exact:true}).press('Enter');await courseReady(p);assert.equal(await form(p,'保存课程修改').getByLabel('教师',{exact:true}).inputValue(),'备份时教师');report.checks.push('restore to verified new dataset preserves old dataset and restores backed-up course');
    await nav(p,'数据与备份');f=form(p,'保存当前副本并回滚');await f.getByLabel('输入当前数据集 ID 确认维护操作',{exact:true}).fill(newId);await f.getByRole('button',{name:'保存当前副本并回滚',exact:true}).click();await success(p,'已回滚到恢复前数据集，并保留回滚前的完整副本。');assert.equal((await pointer()).dataset_id,oldId);
    await nav(p,'课程工作台');await p.getByLabel('搜索课程',{exact:true}).fill(course);await p.getByLabel('搜索课程',{exact:true}).press('Enter');await courseReady(p);assert.equal(await form(p,'保存课程修改').getByLabel('教师',{exact:true}).inputValue(),'恢复前修改教师');report.checks.push('rollback preserves current snapshot and returns to pre-restore edits');
    for(const original of originals){assert.equal(await sha(original.file),original.sha256);assert.equal(String((await fs.stat(original.file,{bigint:true})).mtimeNs),original.mtimeNs);}assert.equal(await sha(path.join(base,'m1','plw.sqlite3')),m1Hash);
    report.checks.push('both original source files and preserved M1 database unchanged');
    assert.deepEqual(report.externalRequests,[]);assert.deepEqual(report.pageErrors,[]);assert.deepEqual(report.consoleErrors,[]);report.checks.push('no observed non-loopback requests or JS/console errors');
    await p.screenshot({path:path.join(base,'browser-m2.png'),fullPage:true});report.passed=true;
  }catch(e){report.passed=false;report.error=e.stack;if(p)await p.screenshot({path:path.join(base,'browser-m2-failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}
  finally{report.finishedAt=new Date().toISOString();await fs.writeFile(path.join(base,'browser-m2.json'),JSON.stringify(report,null,2),'utf8');await context.close();console.log(JSON.stringify(report,null,2));}
})();
