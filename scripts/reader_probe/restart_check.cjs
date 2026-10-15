const fs=require('node:fs/promises'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const [modules,root]=process.argv.slice(2),{chromium}=require(path.join(modules,'playwright'));
(async()=>{
 const before=JSON.parse((await fs.readFile(path.join(root,'evidence','pre-restart.json'),'utf8')).replace(/^\uFEFF/,''));
 const data=await fs.readFile(path.join(root,'annotations.json'));assert.equal(crypto.createHash('sha256').update(data).digest('hex').toUpperCase(),before.Hash);
 const state=JSON.parse(data),fixtures=JSON.parse(await fs.readFile(path.join(root,'fixtures.json'),'utf8'));
 const expected=state.documents[fixtures.files[0].sha256];
 const context=await chromium.launchPersistentContext(path.join(root,'evidence','restart-'+crypto.randomUUID()),{channel:'msedge',headless:true,viewport:{width:1440,height:1100},args:['--disable-background-networking','--disable-component-update','--no-first-run']});
 const external=[];
 try{
  await context.route('**/*',async r=>{if(new URL(r.request().url()).hostname==='127.0.0.1')await r.continue();else{external.push(r.request().url());await r.abort();}});
  if(context.routeWebSocket)await context.routeWebSocket('**/*',ws=>{if(new URL(ws.url()).hostname==='127.0.0.1')ws.connectToServer();else{external.push(ws.url());ws.close();}});
  const p=await context.newPage();await p.goto('http://127.0.0.1:8503');await p.locator('.reader-root[data-ready="true"]').waitFor({timeout:60000});
  assert.equal(Number(await p.locator('.reader-root').getAttribute('data-page')),expected.page);
  assert.equal(Number(await p.locator('.reader-root').getAttribute('data-marks')),expected.marks.length);
  await p.screenshot({path:path.join(root,'evidence','restarted-reader.png'),fullPage:true});
  const after=crypto.createHash('sha256').update(await fs.readFile(path.join(root,'annotations.json'))).digest('hex').toUpperCase();assert.equal(after,before.Hash);assert.equal(external.length,0);
  const report={passed:true,checkedAt:new Date().toISOString(),page:expected.page,marks:expected.marks.length,annotations_hash_unchanged:true,externalRequests:external};
  await fs.writeFile(path.join(root,'evidence','restart-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await context.close();}
})();
