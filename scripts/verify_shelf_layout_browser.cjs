const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');const{chromium}=require('playwright');
(async()=>{
const folder=process.argv[2],cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8')),report={checks:[],fits:[],errors:[]};
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
try{
const context=await browser.newContext({viewport:{width:1600,height:1000}}),p=await context.newPage();p.setDefaultTimeout(30000);p.on('pageerror',e=>report.errors.push(e.message));
await context.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());await p.goto(cfg.origin);
await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await p.waitForTimeout(500);
const main=p.getByTestId('stMain');for(const course of cfg.courses)assert.equal(await main.getByRole('button',{name:course.name,exact:true}).count(),1);
assert.equal(await main.getByRole('button',{name:'已归档测试课',exact:true}).count(),0);report.checks.push('All seven active courses appear on Today; archived course stays excluded');
await main.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();
await p.locator('.reader-root[data-ready="true"]').waitFor();await p.waitForTimeout(600);
assert.equal(await p.getByTestId('stException').count(),0);
const bounds=await p.locator('.reader-root').evaluate(r=>{const b=r.querySelector('.reader-body').getBoundingClientRect(),t=r.getBoundingClientRect();return{reader_top:t.top,body_top:b.top,body_height:b.height,viewport:innerHeight};});await p.screenshot({path:path.join(folder,'shelf-initial.png')});assert.ok(bounds.body_top<300,JSON.stringify(bounds));assert.ok(bounds.body_height>500);report.desktop_bounds=bounds;
for(const title of ['导入课件','调整课件顺序','下载与离线阅读','阅读器维护','课件详情','生成阅读副本 / 添加新版本'])assert.equal(await p.getByText(title,{exact:true}).isVisible(),false,title);
await p.getByRole('button',{name:'课件工具',exact:true}).click();await p.getByText('导入课件',{exact:true}).waitFor();for(const title of ['调整课件顺序','下载与离线阅读','阅读器维护','课件详情'])assert.equal(await p.getByText(title,{exact:true}).isVisible(),true,title);
await p.keyboard.press('Escape');report.checks.push('Reader enters the first screen; secondary import/order/download/maintenance/details controls are accessible inside Courseware Tools');
await p.locator('.reader-root').screenshot({path:path.join(folder,'reader-component.png')});await p.screenshot({path:path.join(folder,'shelf-desktop.png')});
async function stable(label){
 await p.locator('.reader-root[data-ready="true"]').waitFor();await p.waitForTimeout(650);
 const values=await p.locator('.reader-root').evaluate(async r=>{let events=0;const observer=new MutationObserver(()=>events++);observer.observe(r,{attributes:true,attributeFilter:['data-zoom']});const sample=[];for(let n=0;n<15;n++){const c=r.querySelector('.page-scroll'),b=r.querySelector('.paper').getBoundingClientRect();sample.push({zoom:r.dataset.zoom,width:c.clientWidth,height:c.clientHeight,paper_width:b.width,paper_height:b.height,scroll_width:c.scrollWidth,scroll_height:c.scrollHeight});await new Promise(resolve=>setTimeout(resolve,100));}observer.disconnect();return{sample,events};});
 assert.equal(new Set(values.sample.map(x=>x.zoom)).size,1,label+JSON.stringify(values));assert.ok(values.events<=1,label+' repeated fit redraws '+values.events);const last=values.sample.at(-1);assert.ok(last.scroll_width<=last.width+2,label+' horizontal overflow');assert.ok(last.scroll_height<=last.height+2,label+' vertical overflow');report.fits.push({label,...values});
}
for(const width of [1600,1440,1280,1180,1050]){await p.setViewportSize({width,height:1000});await stable('desktop '+width);}
await p.getByLabel('缩放',{exact:true}).selectOption('2.5');await p.waitForTimeout(250);await p.getByLabel('缩放',{exact:true}).selectOption('fit-page');await stable('manual zoom -> fit page');
await p.locator('[data-cmd="rotate"]').click();await stable('rotate');await p.locator('[data-cmd="rotate"]').click();await stable('second rotation');
await p.locator('[data-cmd="thumbnails"]').click();await stable('hide thumbnails');await p.locator('[data-cmd="thumbnails"]').click();await stable('show thumbnails');
await p.setViewportSize({width:820,height:1180});await stable('tablet portrait');await p.screenshot({path:path.join(folder,'shelf-tablet.png')});
await p.getByRole('button',{name:'课件工具',exact:true}).click();assert.equal(await p.getByText('调整课件顺序',{exact:true}).isVisible(),true);await p.keyboard.press('Escape');
await p.getByLabel('选择课件',{exact:true}).click();await p.getByRole('option',{name:'02 纵向旋转课件.pdf',exact:true}).click();await p.locator('.reader-root[data-ready="true"]').waitFor();await stable('portrait PDF');
await p.locator('[data-cmd="rotate"]').click();await stable('portrait PDF rotated');
report.checks.push('Page fit remains constant after viewport changes, manual zoom, rotation, thumbnail toggle and portrait document selection');
assert.equal(await p.getByTestId('stException').count(),0);assert.deepEqual(report.errors,[]);report.passed=true;await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,fits:report.fits.map(({label,events,sample})=>({label,events,zoom:sample.at(-1).zoom}))}));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

