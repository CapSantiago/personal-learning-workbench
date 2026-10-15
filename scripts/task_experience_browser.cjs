// UI acceptance against synthetic data only; never point this at production.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,rootArg]=process.argv.slice(2),root=path.resolve(rootArg);
const rel=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel),'Synthetic workspace required');
const {chromium}=require(path.join(modules,'playwright'));
const out=path.join(root,'evidence'),report={started:new Date().toISOString(),checks:[],external:[],errors:[]};
function check(value){report.checks.push(value);console.log(value);}
const idle=async p=>{await p.waitForTimeout(250);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');assert.equal(await p.getByTestId('stException').count(),0);};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);};
const details=(p,name)=>p.locator('details').filter({has:p.locator('summary').getByText(name,{exact:true})}).first();
async function expand(p,name){const d=details(p,name);if(!await d.evaluate(e=>e.open))await d.locator(':scope > summary').click();}
async function select(p,label,value){const input=p.getByLabel(label,{exact:true});await input.click();await input.fill(value);await p.getByRole('option',{name:value,exact:true}).click();await idle(p);}
async function course(p,name){await p.getByTestId('stSidebar').getByRole('button',{name,exact:true}).click();await p.getByRole('heading',{name,exact:true}).waitFor();await idle(p);}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',async r=>{if(new URL(r.request().url()).origin==='http://127.0.0.1:8505')await r.continue();else{report.external.push(r.request().url());await r.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).origin==='ws://127.0.0.1:8505')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.setDefaultTimeout(20000);p.on('pageerror',e=>report.errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:8505/');await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  assert.equal(await p.getByRole('radiogroup').count(),0);assert.equal(await p.getByTestId('stMetric').count(),0);
  assert.deepEqual((await p.locator('.plw-task-title').allTextContents()).filter(t=>!t.startsWith('日历选择验收')),['复习拉普拉斯变换','完成第二章习题','重要实验提交','准备闭环控制实验','长期课程项目','自由复习']);
  assert.equal(await p.locator('.plw-task-row.is-overdue').count(),1);
  assert.match(await p.locator('.plw-task-row.is-overdue').innerText(),/已逾期/);
  assert.ok((await p.locator('.plw-task-priority.is-important').allTextContents()).every(t=>t==='重要'));
  await p.screenshot({path:path.join(out,'tasks-home-desktop.png'),fullPage:true});
  check('Unified deadline order, overdue mark, importance and tasks beyond seven days');

  const side=p.getByTestId('stSidebar'),shelf=side.getByRole('button',{name:/课程书架/});
  await shelf.click();await idle(p);assert.ok(await p.getByRole('heading',{name:'今日学习',exact:true}).isVisible());
  await course(p,'机器人学');await ready(p);
  assert.equal(await p.getByLabel('选择课程',{exact:true}).count(),0);
  assert.equal(await side.getByRole('button',{name:'机器人学',exact:true}).getAttribute('kind'),'primary');
  await course(p,'自动控制原理');await ready(p);
  await expand(p,'搜索与章节筛选');await p.getByLabel('搜索课件',{exact:true}).fill('不存在的筛选');await p.getByLabel('搜索课件',{exact:true}).press('Enter');await idle(p);
  await course(p,'机器人学');await course(p,'自动控制原理');await ready(p);
  assert.equal(await p.getByLabel('搜索课件',{exact:true}).inputValue(),'');
  await shelf.click();await idle(p);assert.equal(await side.getByRole('button',{name:'机器人学',exact:true}).count(),0);
  assert.ok(await p.getByRole('heading',{name:'自动控制原理',exact:true}).isVisible());await shelf.click();await idle(p);
  check('Sidebar expands courses, opens selected page, clears old filters and collapses independently');

  await course(p,'机器人学');await ready(p);
  const edition=await p.locator('.reader-root').getAttribute('data-doc'),savedPage=await p.locator('.reader-root').getAttribute('data-page');
  await p.getByRole('button',{name:'移除课件',exact:true}).click();await p.getByRole('button',{name:'确认移除',exact:true}).click();await idle(p);
  await p.getByRole('button',{name:'撤销移除',exact:true}).waitFor();assert.equal(await p.getByLabel('选择课件',{exact:true}).count(),0);
  await p.getByRole('button',{name:'撤销移除',exact:true}).click();await ready(p);
  assert.equal(await p.locator('.reader-root').getAttribute('data-doc'),edition);assert.equal(await p.locator('.reader-root').getAttribute('data-page'),savedPage);
  await p.screenshot({path:path.join(out,'sidebar-course-desktop.png'),fullPage:true});
  check('Last courseware can be removed and restored with the same edition and saved page');

  await side.getByRole('button',{name:'任务管理',exact:true}).click();await idle(p);
  assert.equal(await p.getByLabel('选择课程',{exact:true}).inputValue(),'机器人学');
  await expand(p,'添加新任务');
  const taskTitle='日历选择验收 '+Date.now();
  await p.getByLabel('任务标题',{exact:true}).fill(taskTitle);
  await select(p,'截止方式','精确时间（北京时间）');
  await p.getByLabel('截止日期',{exact:true}).click();
  await p.screenshot({path:path.join(out,'task-calendar-popup.png'),fullPage:true});
  report.calendar=await p.getByRole('grid',{name:/Choose date/}).count();
  assert.equal(report.calendar,1,'Date input should open a calendar');
  await p.getByRole('grid',{name:/Choose date/}).getByRole('button',{name:'2026年10月20日星期二',exact:true}).click();
  await p.getByLabel('截止时间（北京时间）',{exact:true}).click();
  await p.getByRole('spinbutton',{name:'分钟, 截止时间（北京时间）',exact:true}).fill('30');
  await p.getByRole('spinbutton',{name:'分钟, 截止时间（北京时间）',exact:true}).press('Tab');
  await select(p,'重要程度','重要');
  await p.getByRole('button',{name:'保存任务',exact:true}).click();await idle(p);
  assert.equal(await p.getByTestId('stAlert').filter({hasText:'操作未完成'}).count(),0);
  await side.getByRole('button',{name:'今日学习',exact:true}).click();await idle(p);
  const created=p.locator('.plw-task-row').filter({has:p.getByText(taskTitle,{exact:true})});
  assert.match(await created.innerText(),/2026-10-20 18:30/);assert.equal(await created.locator('.plw-task-priority').innerText(),'重要');
  check('Calendar popup, hour/minute choice and important-task save appear correctly on home');

  await p.setViewportSize({width:390,height:844});
  await p.waitForTimeout(500);
  const collapse=p.getByTestId('stSidebarCollapseButton').getByRole('button');if(await side.getAttribute('aria-expanded')==='true')await collapse.click();await p.waitForTimeout(350);
  const size=await p.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,main:document.querySelector('[data-testid="stMain"]').clientWidth,scroll:document.querySelector('[data-testid="stMain"]').scrollWidth}));
  assert.ok(size.document<=size.viewport+2&&size.scroll<=size.main+2,JSON.stringify(size));
  await p.screenshot({path:path.join(out,'tasks-home-phone.png'),fullPage:true});
  check('Phone-width task rows wrap without horizontal page overflow');
  assert.deepEqual(report.external,[]);assert.deepEqual(report.errors,[]);report.ok=true;
 }catch(e){report.ok=false;report.failure=e.stack;await p.screenshot({path:path.join(out,'task-experience-failure.png'),fullPage:true});report.dom=(await p.locator('body').innerText()).slice(-8000);throw e;}
 finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'task-experience-browser.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
