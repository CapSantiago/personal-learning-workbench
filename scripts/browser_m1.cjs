/* M1 browser acceptance using bundled Playwright and an isolated Edge profile.
   Start scripts/launch.py --offline-probe, then pass an existing node_modules path. */
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {chromium} = require(path.join(process.argv[2], 'playwright'));
const root = path.resolve(__dirname, '..');
const sandbox = path.join(root, '.sandbox');
const run = crypto.randomUUID().slice(0,8);
const semester = `2026 秋季 · 合成验收 ${run}`;
const course = `控制原理 %_ · 合成验收 ${run}`;
const report = {startedAt:new Date().toISOString(),run,semester,course,checks:[],externalRequests:[],pageErrors:[],consoleErrors:[]};
const settle = async p => p.waitForFunction(() => {
  const labels = Array.from(document.querySelectorAll('[data-testid="stForm"] button[kind$="FormSubmit"]')).map(x=>x.textContent.trim());
  return document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state') === 'notRunning' &&
    !document.querySelector('[data-stale="true"]') && new Set(labels).size === labels.length;
});
const nav = async (p,label) => {await p.getByTestId('stSidebar').getByText(label,{exact:true}).click(); await p.getByRole('heading',{name:label,exact:true}).waitFor(); await settle(p);};
const check = async (p,label) => {if(!await p.getByRole('checkbox',{name:label,exact:true}).isChecked()) await p.getByText(label,{exact:true}).click(); await settle(p);};
const form = (p,label) => p.getByTestId('stForm').filter({has:p.getByRole('button',{name:label,exact:true,includeHidden:true})});
const success = async (p, text) => {await p.getByText(text,{exact:true}).waitFor(); await settle(p);};
const choose = async (scope,label,option) => {
  const control=scope.getByLabel(label,{exact:true});
  if(await control.inputValue()===option) return;
  await control.fill(option);
  await control.press('ArrowDown');
  await scope.page().getByRole('option',{name:option,exact:true}).click();
};
const search = async (p,label,text) => {const input=p.getByLabel(label,{exact:true}); await input.fill(text); await input.press('Enter'); await settle(p);};
const local = u => ['127.0.0.1','localhost','[::1]'].includes(new URL(u).hostname);

(async () => {
  await fs.mkdir(sandbox,{recursive:true});
  const context = await chromium.launchPersistentContext(path.join(sandbox,'browser-profiles',crypto.randomUUID()),{
    channel:'msedge',headless:true,viewport:{width:1440,height:1500},
    args:['--disable-background-networking','--disable-component-update','--no-first-run'],
  });
  try {
    await context.route('**/*',async r => {
      if(local(r.request().url())) await r.continue();
      else {report.externalRequests.push(r.request().url()); await r.abort('blockedbyclient');}
    });
    if(context.routeWebSocket) await context.routeWebSocket('**/*',ws => {
      if(local(ws.url())) ws.connectToServer();
      else {report.externalRequests.push(ws.url()); ws.close();}
    });
    const observe = p => {
      p.on('pageerror',e=>report.pageErrors.push(e.message));
      p.on('console',m=>{if(m.type()==='error')report.consoleErrors.push(m.text());});
    };
    const page = await context.newPage(); observe(page);
    await page.goto('http://127.0.0.1:8501',{waitUntil:'domcontentloaded'});
    await page.getByRole('heading',{name:'Personal Learning Workbench',exact:true}).waitFor();
    await settle(page);
    const initialize=page.getByRole('button',{name:'创建 M1 验收数据集',exact:true});
    if(await initialize.count()) {
      await initialize.click();
      await success(page,'M1 验收数据集已创建。请先到学期管理添加一个学期。');
      report.checks.push('explicit synthetic dataset initialization succeeds');
    }
    await nav(page,'学期管理');
    const semesterForm = form(page,'创建学期');
    await semesterForm.getByLabel('学期名称',{exact:true}).fill(semester);
    await semesterForm.getByLabel('开始日期（可留空）',{exact:true}).fill('2027-02-01');
    await semesterForm.getByLabel('结束日期（可留空）',{exact:true}).fill('2026-01-31');
    await semesterForm.getByRole('button',{name:'创建学期',exact:true}).click();
    await page.getByTestId('stAlert').filter({hasText:'结束日期'}).waitFor();
    await settle(page);
    assert.equal(await semesterForm.getByLabel('学期名称',{exact:true}).inputValue(),semester);
    report.checks.push('invalid date range rejected with form values preserved');
    await semesterForm.getByLabel('开始日期（可留空）',{exact:true}).fill('2026-09-01');
    await semesterForm.getByLabel('结束日期（可留空）',{exact:true}).fill('2027-01-31');
    await semesterForm.getByRole('button',{name:'创建学期',exact:true}).click();
    await success(page,'学期已保存。相同表单再次提交不会重复创建。');
    await semesterForm.getByRole('button',{name:'创建学期',exact:true}).click();
    await success(page,'学期已保存。相同表单再次提交不会重复创建。');
    report.checks.push('semester created and same request replay accepted');
    await nav(page,'课程工作台');
    const newCourse = form(page,'创建课程');
    await choose(newCourse,'所属学期',semester);
    await newCourse.getByLabel('课程名称',{exact:true}).fill(course);
    await newCourse.getByLabel('教师',{exact:true}).fill('示例教师甲');
    await newCourse.getByLabel('学分',{exact:true}).fill('3.5');
    await newCourse.getByLabel('上课时间',{exact:true}).fill('周二 3–4 节');
    await newCourse.getByLabel('考核方式',{exact:true}).fill('实验 40% + 期末 60%');
    await choose(newCourse,'课程状态','学习中');
    await newCourse.getByRole('button',{name:'创建课程',exact:true}).click();
    await success(page,'课程已保存。相同表单再次提交不会重复创建。');
    await newCourse.getByRole('button',{name:'创建课程',exact:true}).click();
    await success(page,'课程已保存。相同表单再次提交不会重复创建。');
    await search(page,'搜索课程',`%_ · 合成验收 ${run}`);
    await page.getByRole('heading',{name:'课程主页',exact:true}).waitFor();
    report.checks.push('course create/replay and Chinese literal %_ search work');
    const second = await context.newPage(); observe(second);
    await second.goto('http://127.0.0.1:8501',{waitUntil:'domcontentloaded'});
    await second.getByRole('heading',{name:'课程工作台',exact:true}).waitFor();
    await search(second,'搜索课程',course);
    const secondEdit=form(second,'保存课程修改');
    await secondEdit.getByLabel('课程名称',{exact:true}).waitFor();
    const edit=form(page,'保存课程修改');
    await edit.getByLabel('教师',{exact:true}).fill('示例教师乙');
    await edit.getByRole('button',{name:'保存课程修改',exact:true}).click();
    await success(page,'课程修改已保存。');
    await secondEdit.getByLabel('课程名称',{exact:true}).fill('此冲突标题不能覆盖已保存课程');
    await secondEdit.getByRole('button',{name:'保存课程修改',exact:true}).click();
    await second.getByTestId('stAlert').filter({hasText:'操作未完成'}).waitFor();
    await settle(second);
    assert.equal(await secondEdit.getByLabel('课程名称',{exact:true}).inputValue(),'此冲突标题不能覆盖已保存课程');
    await second.getByRole('button',{name:'放弃编辑并重新载入课程',exact:true}).click();
    await settle(second);
    await second.waitForFunction(() => Array.from(document.querySelectorAll('input')).some(x=>x.value==='示例教师乙'));
    await settle(second);
    assert.equal(await form(second,'保存课程修改').getByLabel('课程名称',{exact:true}).inputValue(),course);
    report.checks.push('two-session stale edit refused, unsaved values retained, reload shows winning edit');
    await check(page,'显示已归档课程与学期');
    await page.getByRole('button',{name:'归档课程',exact:true}).click();
    await success(page,'课程归档状态已更新，历史数据保留。');
    assert.equal(await form(page,'保存课程修改').getByRole('button',{name:'保存课程修改',exact:true}).isDisabled(),true);
    await page.getByRole('button',{name:'取消课程归档',exact:true}).click();
    await success(page,'课程归档状态已更新，历史数据保留。');
    report.checks.push('course archive/unarchive retains its original learning status');
    await nav(page,'学期管理');
    await search(page,'搜索学期',semester);
    await check(page,'显示已归档学期');
    await page.getByRole('button',{name:'归档学期',exact:true}).click();
    await success(page,'学期归档状态已更新；课程和历史关联均保留。');
    await nav(page,'课程工作台');
    await check(page,'显示已归档课程与学期');
    await search(page,'搜索课程',course);
    await page.getByText('该课程或所属学期已归档。历史信息仍可查看；先取消归档再编辑。',{exact:true}).waitFor();
    assert.equal(await form(page,'保存课程修改').getByRole('button',{name:'保存课程修改',exact:true}).isDisabled(),true);
    await nav(page,'学期管理');
    await check(page,'显示已归档学期');
    await search(page,'搜索学期',semester);
    await page.getByRole('button',{name:'取消学期归档',exact:true}).click();
    await success(page,'学期归档状态已更新；课程和历史关联均保留。');
    report.checks.push('semester archive preserves course history and blocks editing until unarchived');
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByRole('heading',{name:'课程工作台',exact:true}).waitFor();
    await search(page,'搜索课程',course);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('input')).some(x=>x.value==='示例教师乙'));
    assert.equal(await form(page,'保存课程修改').getByLabel('教师',{exact:true}).inputValue(),'示例教师乙');
    await page.getByTestId('stDataFrame').locator('canvas').first().waitFor();
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    await page.screenshot({path:path.join(sandbox,'browser-m1.png'),fullPage:true});
    report.checks.push('browser reload preserves saved course fields');
    assert.deepEqual(report.externalRequests,[]);
    assert.deepEqual(report.pageErrors,[]);
    assert.deepEqual(report.consoleErrors,[]);
    report.checks.push('fresh profile: no non-loopback requests, JavaScript errors or console errors');
    report.passed=true;
  } catch(error) {
    report.passed=false;report.error=error.stack;
    const pages=context.pages();
    for(let i=0;i<pages.length;i++) if(pages[i].url().startsWith('http://127.0.0.1:8501')) {
      await pages[i].screenshot({path:path.join(sandbox,`browser-m1-failure-${i}.png`),fullPage:true});
    }
    throw error;
  }
  finally {
    report.finishedAt=new Date().toISOString();
    await fs.writeFile(path.join(sandbox,'browser-m1.json'),JSON.stringify(report,null,2),'utf8');
    await context.close(); console.log(JSON.stringify(report,null,2));
  }
})().catch(()=>{process.exitCode=1;});
