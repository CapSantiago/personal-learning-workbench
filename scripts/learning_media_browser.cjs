// Test only the synthetic media-service workspace on loopback 8505.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const [modules,rootArg]=process.argv.slice(2),root=path.resolve(rootArg);
const rel=path.relative(path.join(__dirname,'../.sandbox/test-runs'),root);
assert.ok(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel),'Synthetic workspace required');
const {chromium}=require(path.join(modules,'playwright')),out=path.join(root,'evidence');
const report={started:new Date().toISOString(),checks:[],external:[],errors:[],video:[]};
const idle=async p=>{await p.waitForTimeout(220);await p.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');assert.equal(await p.getByTestId('stException').count(),0);};
const ready=async p=>{await p.locator('.reader-root[data-ready="true"]').waitFor();await idle(p);};
const detail=(p,name)=>p.locator('details').filter({has:p.locator(':scope > summary').getByText(name,{exact:true})}).first();
async function expand(p,name){const d=detail(p,name);if(!await d.evaluate(e=>e.open))await d.locator(':scope > summary').click();return d;}
async function select(p,label,value){const input=p.getByLabel(label,{exact:true});await input.click();await input.fill(value);await p.getByRole('option',{name:value,exact:true}).click();await idle(p);}
function check(value){report.checks.push(value);console.log(value);}
async function play(p,label){
 const v=p.locator('video');await v.waitFor();await p.waitForFunction(()=>{const v=document.querySelector('video');return v&&v.readyState>=2&&v.videoWidth>0;});
 const result=await v.evaluate(async v=>{v.muted=true;await v.play();await new Promise(r=>setTimeout(r,350));const moving=v.currentTime;v.pause();const target=Math.min(1.5,v.duration*.6);v.currentTime=target;await new Promise((resolve,reject)=>{if(Math.abs(v.currentTime-target)<.05&&!v.seeking)return resolve();v.addEventListener('seeked',resolve,{once:true});setTimeout(()=>reject(new Error('Video did not seek')),5000);});return {width:v.videoWidth,height:v.videoHeight,duration:v.duration,moving,seek:v.currentTime,src:v.getAttribute('src'),inline:v.hasAttribute('playsinline')};});
 assert.ok(result.moving>0&&result.seek>0&&result.duration>0&&result.inline);assert.ok(result.src.startsWith('/plw-reader/'));
 report.video.push({label,...result});
 const range=await p.evaluate(async src=>{let r=await fetch(src,{headers:{Range:'bytes=0-15'}});return {status:r.status,body:(await r.arrayBuffer()).byteLength,range:r.headers.get('Content-Range')};},result.src);
 assert.equal(range.status,206);assert.equal(range.body,16);assert.match(range.range,/^bytes 0-15\//);
}
(async()=>{
 const setup=JSON.parse(await fs.readFile(path.join(out,'experience-setup.json'),'utf8'));
 const b=await chromium.launch({channel:'msedge',headless:true,args:['--disable-background-networking','--no-first-run']});
 const context=await b.newContext({viewport:{width:1440,height:1080}});
 await context.route('**/*',async r=>{if(new URL(r.request().url()).origin==='http://127.0.0.1:8505')await r.continue();else{report.external.push(r.request().url());await r.abort();}});
 await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).origin==='ws://127.0.0.1:8505')ws.connectToServer();else{report.external.push(ws.url());ws.close();}});
 const p=await context.newPage();p.setDefaultTimeout(30000);p.on('pageerror',e=>report.errors.push(e.message));
 try{
  await p.goto('http://127.0.0.1:8505');await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await idle(p);
  const side=p.getByTestId('stSidebar');await side.getByRole('button',{name:/课程书架/}).click();await idle(p);
  const list=side.locator('.st-key-sidebar_course_list');let before=await list.getByRole('button').allTextContents();
  const target=before.at(-1).trim();await list.getByRole('button',{name:target,exact:true}).click();await idle(p);
  await p.getByRole('button',{name:'课程选项',exact:true}).click();await p.getByLabel('课程移至第几门',{exact:true}).fill('1');await p.getByLabel('课程移至第几门',{exact:true}).press('Enter');await idle(p);
  await p.getByRole('button',{name:'移动课程到此位置',exact:true}).click();await idle(p);
  assert.equal((await list.getByRole('button').allTextContents())[0].trim(),target);
  await p.reload();await p.getByRole('heading',{name:'今日学习',exact:true}).waitFor();await side.getByRole('button',{name:/课程书架/}).click();await idle(p);
  assert.equal((await list.getByRole('button').allTextContents())[0].trim(),target);
  await list.getByRole('button',{name:'排序课程 A',exact:true}).click();await idle(p);
  await p.getByRole('button',{name:'课程选项',exact:true}).click();await p.getByRole('button',{name:'确认移除课程',exact:true}).click();await idle(p);
  assert.equal(await list.getByRole('button',{name:'排序课程 A',exact:true}).count(),0);
  await p.getByRole('button',{name:'撤销课程删除',exact:true}).click();await idle(p);
  assert.equal((await list.getByRole('button').allTextContents()).at(-1).trim(),'排序课程 A');
  check('Course order persists after reload; removal hides course; undo restores it at the end');

  await list.getByRole('button',{name:setup.course,exact:true}).click();await ready(p);
  await select(p,'选择课件','OCR 合成扫描课件.pdf');await ready(p);
  let ocr=await expand(p,'图片文字识别（OCR）');await ocr.getByRole('button',{name:'识别当前页',exact:true}).click();await p.getByText('当前页文字已识别，可在课件内查找。',{exact:true}).waitFor();await ready(p);
  ocr=await expand(p,'图片文字识别（OCR）');await p.getByTestId('stCode').filter({hasText:/OCR/}).waitFor();
  const recognized=await ocr.getByTestId('stCode').first().innerText();assert.match(recognized.replace(/\s/g,''),/机器人学习工作台/);
  await p.locator('.reader-root .search-panel > summary').click();await p.getByLabel('课件内查找',{exact:true}).fill('机器人学习工作台');await p.getByLabel('课件内查找',{exact:true}).press('Enter');
  await p.locator('.reader-root[data-search-state="done"]').waitFor();assert.ok(await p.locator('.search-result').count()>0);
  await p.locator('.search-result').first().click();await ready(p);
  await p.screenshot({path:path.join(out,'ocr-search-desktop.png'),fullPage:true});
  check('Actual offline scanned-page OCR integrates with reader search and page jumping');

  ocr=await expand(p,'图片文字识别（OCR）');await expand(p,'识别单张图片');
  await ocr.locator('input[type=file]').setInputFiles(path.join(root,'sources/OCR 图片.png'));
  await idle(p);await expand(p,'图片文字识别（OCR）');await expand(p,'识别单张图片');
  await ocr.getByRole('button',{name:'识别图片文字',exact:true}).click();await idle(p);
  await ocr.getByRole('button',{name:'导出图片文字',exact:true}).waitFor();
  assert.match((await ocr.getByTestId('stCode').last().innerText()).replace(/\s/g,''),/OCRTEST2026/);
  check('Image selection, actual PNG OCR, copyable text and export controls');

  for(const [name,button,label] of [['synthetic-embedded-video.pptx','读取课件内视频','embedded'],['synthetic-animation.pptx','生成动画播放版','animation']]){
   await select(p,'选择课件',name);await ready(p);const panel=await expand(p,'动画与视频');
   const toggle=p.getByLabel('显示播放与准备工具',{exact:true});if(!await toggle.isChecked())await panel.getByText('显示播放与准备工具',{exact:true}).click();await idle(p);
   await panel.getByRole('button',{name:button,exact:true}).click();await p.getByText(label==='embedded'?'视频检查完成。':'动画播放版已准备好。',{exact:true}).waitFor();await idle(p);await expand(p,'动画与视频');await play(p,label);
   await p.screenshot({path:path.join(out,`${label}-video-desktop.png`),fullPage:true});
  }
  check('Embedded PPTX video and freshly generated animation MP4 play inline, pause, seek and serve byte ranges');
  await p.setViewportSize({width:820,height:1180});await p.waitForTimeout(500);
  const dims=await p.locator('video').evaluate(v=>({width:v.getBoundingClientRect().width,view:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(dims.width<=dims.view&&dims.scroll<=dims.view+2);await play(p,'tablet viewport');
  await p.screenshot({path:path.join(out,'animation-tablet.png'),fullPage:true});
  check('Tablet-width layout preserves inline playback without horizontal overflow');
  assert.deepEqual(report.external,[]);assert.deepEqual(report.errors,[]);report.ok=true;
 }catch(e){report.ok=false;report.failure=e.stack;report.dom=(await p.locator('body').innerText()).slice(-8000);await p.screenshot({path:path.join(out,'learning-media-failure.png'),fullPage:true});throw e;}
 finally{report.finished=new Date().toISOString();await fs.writeFile(path.join(out,'learning-media-browser.json'),JSON.stringify(report,null,2));await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
