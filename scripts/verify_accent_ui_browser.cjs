/* Reproduce the reported header and active-sidebar hover before applying fixes. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const folder=process.argv[2],phase=process.argv[3],cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8'));
 const report={phase,checks:[],headers:[],hover:[],themes:[],errors:[]};
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const c=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await c.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());
  const p=await c.newPage();p.setDefaultTimeout(25000);p.on('pageerror',e=>report.errors.push(e.message));
  const main=p.getByTestId('stMain'),side=p.getByTestId('stSidebar');
  const idle=async()=>p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');
  const luminance=color=>{const channels=color.startsWith('#')?color.match(/[a-f\d]{2}/gi).map(n=>parseInt(n,16)):color.match(/[\d.]+/g).slice(0,3).map(Number);return channels.map(n=>n/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((a,n,i)=>a+n*[.2126,.7152,.0722][i],0)};
  const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
  async function openSide(){const opener=p.getByTestId('stExpandSidebarButton');if(await opener.isVisible())await opener.click();}
  async function appearance(){
   await idle();await openSide();
   const details=side.locator('details').filter({has:p.locator('summary').getByText('课程与设置',{exact:true})});
   // Native Streamlit disclosures finish closing after script-state is idle.
   // Inspect the settled state; an open attribute alone also describes closing.
   await details.evaluate(async e=>{await Promise.all(e.getAnimations().map(a=>a.finished.catch(()=>{})))});
   if(!(await details.evaluate(e=>e.open)))await details.locator('summary').click();
   await details.locator('[data-testid="stExpanderDetails"]:not([inert])').waitFor();
   await side.getByRole('button',{name:'外观设置',exact:true}).click();
   await main.getByRole('heading',{name:'外观设置',exact:true}).waitFor();await idle();
  }
  async function shelf(){await openSide();await side.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();await p.locator('.reader-root[data-ready="true"]').waitFor();await idle();}
  const backgrounds=async()=>p.evaluate(()=>({main:getComputedStyle(document.querySelector('[data-testid="stAppViewContainer"]')).backgroundColor,sidebar:getComputedStyle(document.querySelector('[data-testid="stSidebar"]')).backgroundColor}));
  await p.goto(cfg.origin);await main.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();await idle();
  await p.locator('.reader-root[data-ready="true"]').waitFor();
  async function header(label){await idle();await p.waitForTimeout(200);
   const item=await p.locator('.st-key-shelf_heading').evaluate(e=>{
    const caption=e.querySelector('[data-testid="stCaptionContainer"] p'),heading=e.querySelector('h2'),next=document.querySelector('.st-key-shelf_switcher');
    const rect=n=>{const r=n.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom}};
    const range=document.createRange();range.selectNodeContents(caption);return{heading:rect(heading),caption:rect(caption),text:rect(range),parent:rect(e),next:rect(next)};
   });report.headers.push({label,...item});
   if(!phase.includes('before'))assert.ok(item.next.y>=Math.max(item.caption.bottom,item.text.bottom)+3,JSON.stringify(item));
  }
  await header('desktop');await p.screenshot({path:path.join(folder,'reader.png')});
  await side.getByRole('button',{name:'任务管理',exact:true}).click();await idle();
  const task=side.getByRole('button',{name:'任务管理',exact:true});await task.hover();
  const style=await task.evaluate(e=>({background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e.querySelector('p')).color,icon:getComputedStyle(e,'::before').backgroundColor,shadow:getComputedStyle(e).boxShadow}));
  report.hover.push(style);await side.screenshot({path:path.join(folder,'hover.png')});
  if(!phase.includes('before'))assert.notEqual(style.background,style.text,'Hovered label is hidden by its own background');
  if(!phase.includes('before')){
   assert.ok(contrast(style.text,style.background)>=4.5);assert.equal(style.text,style.icon);
   const bg=await backgrounds();
   await appearance();
   for(const [id,label] of [['green','绿色'],['black','黑色'],['purple','紫色'],['blue','蓝色'],['yellow','黄色'],['orange','橙色']]){
    await p.getByLabel('主题强调色',{exact:true}).click();await p.getByRole('option',{name:label,exact:true}).click();await p.getByRole('button',{name:'保存主题颜色',exact:true}).click();await idle();
    await p.mouse.move(500,500);const button=p.getByRole('button',{name:'保存主题颜色',exact:true});
    const value=await button.evaluate(e=>({accent:getComputedStyle(document.documentElement).getPropertyValue('--plw-accent').trim(),background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e.querySelector('p')).color,border:getComputedStyle(e).borderColor,kind:e.getAttribute('kind')}));
    assert.ok(contrast(value.text,value.background)>=4.5,id+' solid button contrast '+JSON.stringify(value));
    assert.ok(Math.abs(luminance(value.accent)-luminance(value.background))<.0001,id+' form button did not adopt theme');
    await button.hover();const hover=await button.evaluate(e=>({background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e.querySelector('p')).color}));assert.ok(contrast(hover.text,hover.background)>=4.5,id+' hover contrast');
    const selected=side.getByRole('button',{name:'外观设置',exact:true});await selected.hover();const nav=await selected.evaluate(e=>({background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e.querySelector('p')).color}));assert.ok(contrast(nav.text,nav.background)>=4.5,id+' sidebar hover contrast');
    assert.deepEqual(await backgrounds(),bg,id+' recolored page background');
    report.themes.push({id,...value,hover,nav});
    await side.locator('.plw-brand-lockup').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(folder,'theme-'+id+'.png')});
    if(['purple','yellow'].includes(id)){
     await shelf();const reader=await p.locator('.reader-root').evaluate(r=>({accent:getComputedStyle(r).getPropertyValue('--plw-accent').trim(),text:getComputedStyle(r.querySelector('[data-cmd="pan"]')).color,background:getComputedStyle(r.querySelector('[data-cmd="pan"]')).backgroundColor}));assert.equal(reader.accent,value.accent);assert.ok(contrast(reader.text,reader.background)>=4.5);
     await header(id+' reader');await p.getByRole('button',{name:'课程选项',exact:true}).click();await p.getByText('此设备课件下载库',{exact:true}).click();await p.locator('.device-library .update-all:enabled').waitFor();const library=await p.locator('.device-library .update-all').evaluate(e=>({background:getComputedStyle(e).backgroundColor,text:getComputedStyle(e).color}));assert.ok(contrast(library.text,library.background)>=4.5);assert.ok(Math.abs(luminance(value.accent)-luminance(library.background))<.0001);
     const options=p.getByRole('button',{name:'课程选项',exact:true});if(await options.getAttribute('aria-expanded')==='true')await options.click();await appearance();
    }
   }
   assert.equal(new Set(report.themes.map(t=>t.accent)).size,6);report.checks.push('Six accents persist through native save; page/sidebar backgrounds fixed; solid, hovered, sidebar, reader and library text remain readable');
   const saved=report.themes.at(-1).accent;await p.reload();await main.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle();assert.equal(await p.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--plw-accent').trim()),saved);
   report.progress_dom=await p.getByTestId('stProgress').first().evaluate(e=>e.innerHTML.slice(0,2000));
   await main.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();await p.locator('.reader-root[data-ready="true"]').waitFor();
   for(const width of [1440,1024,768,375]){await p.setViewportSize({width,height:1000});await header('viewport '+width);assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
   await p.setViewportSize({width:375,height:1000});const large=await p.addStyleTag({content:'html{font-size:200%!important}'});await header('200% root text');await large.evaluate(e=>e.remove());
   await openSide();await side.getByRole('button',{name:cfg.courses.at(-1).name,exact:true}).click();await header('long Chinese course title');await p.screenshot({path:path.join(folder,'header-mobile-long.png')});
   await p.setViewportSize({width:1440,height:1000});await appearance();await p.getByRole('button',{name:'恢复默认绿色',exact:true}).click();await p.waitForFunction(expected=>getComputedStyle(document.documentElement).getPropertyValue('--plw-accent').trim()===expected,report.themes[0].accent);await idle();
   await side.locator('.plw-brand-lockup').screenshot({path:path.join(folder,'brand.png')});report.checks.push('Reload restores saved theme; desktop/mobile/200%/long-title header has no overlap; restore default works');
   assert.deepEqual(report.errors,[]);
  }
  report.passed=true;
 }finally{await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
