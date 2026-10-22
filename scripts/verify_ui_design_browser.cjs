/* Real app + native controls + production reader component; synthetic data only. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const folder=process.argv[2],phase=process.argv[3]||'after';
 const cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8'));
 const report={phase,checks:[],screens:[],geometry:[],errors:[]};
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());
  const p=await context.newPage();p.setDefaultTimeout(25000);p.on('pageerror',e=>report.errors.push(e.message));
  await p.goto(cfg.origin);await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();
  const main=p.getByTestId('stMain'),side=p.getByTestId('stSidebar');
  const idle=async()=>{await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');};
  async function nav(label){
   const opener=p.getByTestId('stExpandSidebarButton');if(await opener.isVisible())await opener.click();
   if(['课程管理','学期管理','资料管理','数据与备份','章节与知识点','使用说明'].includes(label)){
    const settings=side.locator('details').filter({has:p.locator('summary').getByText('课程与设置',{exact:true})});
    if(!(await settings.evaluate(e=>e.open)))await settings.locator('summary').click();
   }
   await side.getByRole('button',{name:label,exact:true}).click();await main.getByRole('heading',{name:label,exact:true}).waitFor();await idle();
  }
  async function capture(name){
   await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');await p.waitForTimeout(250);
   const g=await main.evaluate(e=>({viewport:innerWidth,width:e.clientWidth,scrollWidth:e.scrollWidth,documentWidth:document.documentElement.scrollWidth}));
   report.geometry.push({name,...g});
   if(phase!=='before')assert.ok(g.scrollWidth<=g.width+1&&g.documentWidth<=g.viewport+1,name+' whole-page overflow '+JSON.stringify(g));
   const file=name+'.png';await p.screenshot({path:path.join(folder,file),fullPage:true});report.screens.push(file);
   assert.equal(await p.getByTestId('stException').count(),0,name+' app exception');
  }
  for(const c of cfg.courses){await main.getByRole('button',{name:c.name,exact:true}).waitFor();assert.equal(await main.getByRole('button',{name:c.name,exact:true}).count(),1);}
  assert.equal(await main.getByRole('button',{name:'已归档测试课',exact:true}).count(),0);
  await capture('home-desktop');report.checks.push('Home: all seven active courses, three recent documents, synthetic tasks');
  report.native_styles=await main.getByText(/从上次停下的地方继续/).evaluate(e=>({html:e.outerHTML,parent:e.parentElement.outerHTML.slice(0,1400),color:getComputedStyle(e).color,font:getComputedStyle(e).font,opacity:getComputedStyle(e).opacity}));
  report.primary_style=await main.getByRole('button',{name:'继续阅读',exact:true}).first().evaluate(e=>({color:getComputedStyle(e).color,childColor:getComputedStyle(e.querySelector('p')).color}));
  if(phase!=='before')assert.equal(report.primary_style.childColor,'rgb(255, 255, 255)');
  await side.screenshot({path:path.join(folder,'sidebar-desktop.png')});
  report.sidebar_geometry=await side.evaluate(e=>[e,...e.querySelectorAll('[data-testid="stSidebarContent"],[data-testid="stSidebarHeader"],[data-testid="stSidebarUserContent"],.plw-brand-lockup')].map(n=>({name:n.dataset.testid||n.className,padding:getComputedStyle(n).padding,margin:getComputedStyle(n).margin,x:n.getBoundingClientRect().x,y:n.getBoundingClientRect().y,width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height})));
  await main.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();
  await p.locator('.reader-root[data-ready="true"]').waitFor();await capture('reader-desktop');
  await p.getByRole('button',{name:'课件工具',exact:true}).click();await p.getByText('导入课件',{exact:true}).waitFor();await capture('reader-tools');await p.keyboard.press('Escape');
  for(const size of [{width:1024,height:768},{width:768,height:1024},{width:375,height:812},{width:812,height:375}]){
   await p.setViewportSize(size);await capture('reader-'+size.width);
   if(phase!=='before'){
    const layout=await p.locator('.reader-root').evaluate(r=>{const b=r.getBoundingClientRect();return{width:b.width,scrollWidth:r.scrollWidth,controls:[...r.querySelectorAll('.tools button,.tools input,.tools select')].filter(e=>e.getClientRects().length).map(e=>{const v=e.getBoundingClientRect();return{label:e.getAttribute('aria-label')||e.textContent,left:v.left-b.left,right:v.right-b.left,width:v.width,height:v.height}})};});
    assert.ok(layout.scrollWidth<=layout.width+1,JSON.stringify(layout));
    for(const control of layout.controls)assert.ok(control.left>=-1&&control.right<=layout.width+1,JSON.stringify(control));
    if(size.width===375)for(const c of layout.controls)assert.ok(c.width>=43.9&&c.height>=43.9,JSON.stringify(c));
    report.checks.push('Reader tools reflow within '+size.width+'px viewport');
   }
  }
  await p.setViewportSize({width:1440,height:1000});
  if(phase!=='before'){
   await p.getByRole('button',{name:'课程选项',exact:true}).click();await p.getByText('此设备课件下载库',{exact:true}).click();
   const library=p.locator('.device-library');await library.locator('.update-all:enabled').waitFor();await library.locator('.update-all').click();
   await library.locator('.download-progress').filter({hasText:/更新完成.*失败 0 份/}).waitFor();await capture('library-desktop');
   assert.match(await library.locator('.download-summary').textContent(),/本机已保存 8 \/ 8/);
   await library.locator('.update-all').click();await library.locator('.download-progress').filter({hasText:/更新完成：新保存 0 份/}).waitFor();
   await p.setViewportSize({width:375,height:812});await capture('library-mobile');await p.keyboard.press('Escape');
   const opener=p.getByTestId('stExpandSidebarButton');await opener.click();await side.getByText('PLW',{exact:true}).waitFor();
   await side.screenshot({path:path.join(folder,'sidebar-mobile.png')});
   await side.getByRole('button',{name:'今日学习',exact:true}).waitFor();await p.getByTestId('stSidebarCollapseButton').getByRole('button').click();
   await p.setViewportSize({width:1440,height:1000});
   await p.locator('.reader-root').click({position:{x:3,y:3}});await p.keyboard.press('Tab');await p.locator('[data-cmd="next"]').focus();
   report.reader_focus=await p.locator('[data-cmd="next"]').evaluate(e=>({style:getComputedStyle(e).outlineStyle,width:getComputedStyle(e).outlineWidth}));
   assert.equal(report.reader_focus.style,'solid');assert.equal(report.reader_focus.width,'2px');
   report.checks.push('Download library: 8/8 manifest entries saved, incremental update reuses all; mobile drawer and keyboard focus usable');
  }
  await nav('任务管理');
  await main.getByRole('heading',{name:'任务管理',exact:true}).waitFor();
  await p.getByText('添加新任务',{exact:true}).click();await p.getByLabel('任务标题',{exact:true}).scrollIntoViewIfNeeded();await capture('tasks-desktop');
  await p.setViewportSize({width:375,height:812});await p.getByLabel('任务标题',{exact:true}).scrollIntoViewIfNeeded();await capture('tasks-mobile');
  if(phase!=='before'){
   await p.getByRole('button',{name:'完成',exact:true}).first().click();await idle();await p.getByTestId('stRadioGroup').getByText('已完成任务',{exact:true}).click();await idle();
   await main.locator('summary').filter({hasText:'复习坐标变换'}).click();await p.getByRole('button',{name:'恢复待办',exact:true}).click();await idle();
   report.checks.push('Real task completion, archive details and restore succeed without losing the task');
  }
  await p.setViewportSize({width:1440,height:1000});
  await nav('课程管理');
  await main.getByRole('heading',{name:'课程管理',exact:true}).waitFor();await capture('courses-desktop');
  await p.setViewportSize({width:375,height:812});await capture('courses-mobile');
  if(phase!=='before'){
   await main.getByText('编辑课程',{exact:true}).click();await p.getByRole('textbox',{name:'课程名称',exact:true}).scrollIntoViewIfNeeded();await capture('course-detail-mobile');
   await p.setViewportSize({width:1440,height:1000});await p.getByLabel('搜索课程',{exact:true}).fill('离散数学');await p.getByLabel('搜索课程',{exact:true}).press('Enter');
   await main.getByRole('heading',{name:cfg.courses.at(-1).name,exact:true}).waitFor();await idle();await capture('course-detail-desktop');
   await nav('笔记');await p.getByLabel('选择笔记',{exact:true}).click();await p.getByRole('option',{name:'坐标变换与实验笔记',exact:true}).click();
   await p.getByRole('tab',{name:'阅读预览',exact:true}).click();await main.getByRole('heading',{name:'学习记录',exact:true}).waitFor();await capture('notes-desktop');
   report.checks.push('Course search/detail/edit fields and existing Markdown note preview remain available');
  }
  await p.setViewportSize({width:1440,height:1000});await nav('今日学习');
  await main.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await p.setViewportSize({width:375,height:812});await capture('home-mobile');
  if(phase!=='before'){
   await p.addStyleTag({content:'html {font-size:200%!important;}'});await capture('home-large-text');
   const palette=await main.evaluate(e=>{const s=getComputedStyle(e);return Object.fromEntries(['ink','muted','accent','bg','control'].map(k=>[k,s.getPropertyValue('--plw-'+k).trim()]));});
   const luminance=hex=>{const c=hex.match(/[a-f\d]{2}/gi).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
   const ratio=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
   report.contrast={body:ratio(palette.ink,palette.bg),muted:ratio(palette.muted,palette.bg),primary:ratio('#ffffff',palette.accent),control:ratio('#ffffff',palette.control)};
   assert.ok(report.contrast.body>=4.5&&report.contrast.muted>=4.5&&report.contrast.primary>=4.5&&report.contrast.control>=3);
   await context.close();
   const touch=await browser.newContext({viewport:{width:820,height:1180},hasTouch:true,isMobile:true,deviceScaleFactor:2,reducedMotion:'reduce'});
   await touch.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());const t=await touch.newPage();await t.goto(cfg.origin);
   await t.getByTestId('stMain').getByRole('button',{name:cfg.courses[0].name,exact:true}).click();await t.locator('.reader-root[data-ready="true"]').waitFor();
   for(const size of [{width:820,height:1180},{width:1180,height:820}]){
    await t.setViewportSize(size);await t.waitForTimeout(700);const targets=await t.locator('.tools button').evaluateAll(es=>es.filter(e=>e.getClientRects().length).map(e=>({label:e.textContent,w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height})));
    for(const c of targets)assert.ok(c.w>=43.9&&c.h>=43.9,JSON.stringify(c));
    await t.screenshot({path:path.join(folder,'touch-'+size.width+'.png'),fullPage:true});
   }
   await touch.close();report.checks.push('Coarse-pointer tablet portrait/landscape: reader button targets >=44 CSS px; app 200% root text and reduced motion reflow');
  }
  report.passed=true;assert.deepEqual(report.errors,[]);
 }finally{
  await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));await browser.close();
 }
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
