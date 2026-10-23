const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const folder=process.argv[2],phase=process.argv[3],cfg=JSON.parse(await fs.readFile(path.join(folder,'config.json'),'utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true}),report={home:[],reader:[],errors:[]};
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  await context.route('**/*',r=>new URL(r.request().url()).origin===cfg.origin?r.continue():r.abort());
  const p=await context.newPage();p.on('pageerror',e=>report.errors.push(e.message));
  await p.goto(cfg.origin);await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();
  const home=p.locator('.st-key-home_courses');
  for(const width of [1440,1024,768,375]){
   await p.setViewportSize({width,height:1000});await home.getByRole('button',{name:cfg.courses[0].name,exact:true}).hover();
   const g=await home.evaluate(e=>{const h=e.querySelector('h3'),b=e.querySelector('button'),r=document.createRange();r.selectNodeContents(h);return{heading:h.getBoundingClientRect().toJSON(),text:r.getBoundingClientRect().toJSON(),button:b.getBoundingClientRect().toJSON(),styles:[h,h.parentElement,h.parentElement.parentElement].map(n=>({html:n.outerHTML.slice(0,350),margin:getComputedStyle(n).margin,height:getComputedStyle(n).height})),blocks:[...e.children].map(n=>({rect:n.getBoundingClientRect().toJSON(),margin:getComputedStyle(n).margin})),overflow:document.documentElement.scrollWidth>innerWidth}});
   report.home.push({width,...g});await p.screenshot({path:path.join(folder,'home-'+width+'.png')});
   if(!phase.includes('before')){assert.ok(g.button.y>=g.text.bottom+8,JSON.stringify(g));assert.equal(g.overflow,false);}
  }
  await p.setViewportSize({width:1440,height:1000});await home.getByRole('button',{name:cfg.courses[0].name,exact:true}).click();await p.locator('.reader-root[data-ready="true"]').waitFor();
  for(const size of [{width:1440,height:1000},{width:1024,height:768},{width:768,height:1024},{width:375,height:812}]){
   await p.setViewportSize(size);await p.waitForTimeout(400);
   const main=p.getByTestId('stMain');await main.evaluate(e=>e.scrollTop=e.scrollHeight);await p.waitForTimeout(200);
   const g=await p.locator('.reader-root').evaluate(e=>({root:e.getBoundingClientRect().toJSON(),paper:e.querySelector('.paper').getBoundingClientRect().toJSON(),height:e.querySelector('.reader-body').clientHeight,zoom:e.dataset.zoom,padding:getComputedStyle(document.querySelector('[data-testid="stMainBlockContainer"]')).paddingBottom,viewport:innerHeight,scroll:document.querySelector('[data-testid="stMain"]').scrollTop}));
   report.reader.push({...size,...g});await p.screenshot({path:path.join(folder,'scroll-'+size.width+'.png')});
   if(!phase.includes('before')){assert.ok(parseFloat(g.padding)>=size.height*.3);assert.ok(g.root.top<64);}
   // Scrolling the outer page must not resize/re-fit the PDF.
   await main.evaluate(e=>e.scrollTop=Math.max(0,e.scrollTop-150));await p.waitForTimeout(200);
   assert.equal(await p.locator('.reader-root').getAttribute('data-zoom'),g.zoom);
   assert.equal(await p.locator('.reader-body').evaluate(e=>e.clientHeight),g.height);
  }
  assert.deepEqual(report.errors,[]);report.passed=true;
 }finally{await fs.writeFile(path.join(folder,'report.json'),JSON.stringify(report,null,2));await browser.close();}
 console.log(JSON.stringify({passed:report.passed,home:report.home.length,reader:report.reader.length,folder}));
})().catch(e=>{console.error(e);process.exitCode=1});
