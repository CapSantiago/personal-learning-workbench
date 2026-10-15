/* Optional M0 browser verification using an already installed Playwright runtime.
   Usage: node browser_smoke.cjs <absolute bundled node_modules path>
   Fresh Edge profile, fixtures and evidence stay inside this project's .sandbox. */
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {chromium} = require(path.join(process.argv[2], 'playwright'));
const project = path.resolve(__dirname, '..');
const sandbox = path.join(project, '.sandbox');
const origin = 'http://127.0.0.1:8501';
const report = {startedAt: new Date().toISOString(), checks: [], externalRequests: [], pageErrors: [], consoleErrors: []};
const source = path.join(sandbox, 'm0', 'sources', '合成资料 中文 空格.txt');
const sha = async p => crypto.createHash('sha256').update(await fs.readFile(p)).digest('hex');
const local = url => ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(url).hostname);
const settle = async p => p.waitForFunction(() =>
  document.querySelectorAll('button[kind="secondaryFormSubmit"]').length === 1 &&
  !document.querySelector('[data-stale="true"]'));

(async () => {
  await fs.mkdir(sandbox, {recursive:true});
  const profile = path.join(sandbox, 'browser-profiles', crypto.randomUUID());
  const context = await chromium.launchPersistentContext(profile, {
    channel:'msedge', headless:true, viewport:{width:1440,height:1100},
    args:['--disable-background-networking','--disable-component-update','--no-first-run'],
  });
  try {
    await context.route('**/*', async route => {
      const url = route.request().url();
      if (local(url)) await route.continue();
      else { report.externalRequests.push(url); await route.abort('blockedbyclient'); }
    });
    if (context.routeWebSocket) {
      await context.routeWebSocket('**/*', ws => {
        if (local(ws.url())) ws.connectToServer();
        else { report.externalRequests.push(ws.url()); ws.close(); }
      });
    }
    const page = await context.newPage();
    const observe = p => {
      p.on('pageerror', e => report.pageErrors.push(e.message));
      p.on('console', msg => {if(msg.type()==='error') report.consoleErrors.push(msg.text());});
    };
    observe(page);
    await page.goto(origin, {waitUntil:'domcontentloaded'});
    await page.getByRole('heading', {name:'Personal Learning Workbench',exact:true}).waitFor();
    await page.getByRole('button', {name:'生成合成样例',exact:true}).click();
    await page.getByText('合成文本、PDF 和演示数据库已就绪。已有样例不会被覆盖。', {exact:true}).waitFor();
    await settle(page);
    const initialHash = await sha(source);
    const count = async p => Number(await p.locator('[data-testid="stMetricValue"]').innerText());
    const before = await count(page);
    const operation = crypto.randomUUID();
    await page.getByLabel('操作 ID', {exact:true}).fill(operation);
    await page.getByRole('button', {name:'提交验证',exact:true}).click();
    await page.waitForFunction(n => Number(document.querySelector('[data-testid="stMetricValue"]')?.textContent) === n, before+1);
    await settle(page);
    await page.getByRole('button', {name:'提交验证',exact:true}).click();
    await page.getByText('提交成功；相同操作 ID 不会重复添加。', {exact:true}).waitFor();
    await settle(page);
    assert.equal(await count(page), before+1);
    report.checks.push('managed_copy and repeated submit add exactly one record');
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByRole('heading', {name:'Personal Learning Workbench',exact:true}).waitFor();
    await settle(page);
    assert.equal(await count(page), before+1);
    report.checks.push('browser refresh adds no record');
    const page2 = await context.newPage();
    observe(page2);
    await page2.goto(origin, {waitUntil:'domcontentloaded'});
    await settle(page2);
    await page2.getByLabel('操作 ID', {exact:true}).fill(operation);
    await page2.getByRole('button', {name:'提交验证',exact:true}).click();
    await page2.getByText('提交成功；相同操作 ID 不会重复添加。', {exact:true}).waitFor();
    await settle(page2);
    assert.equal(await count(page2), before+1);
    report.checks.push('second browser session replays the same operation without duplication');
    await page.getByRole('button', {name:'使用新的操作 ID',exact:true}).click();
    await settle(page);
    await page.getByRole('combobox').click();
    await page.getByRole('option', {name:'外部引用 (external_reference)',exact:true}).click();
    await page.getByRole('button', {name:'提交验证',exact:true}).click();
    await page.waitForFunction(n => Number(document.querySelector('[data-testid="stMetricValue"]')?.textContent) === n, before+2);
    await settle(page);
    assert.equal(await sha(source), initialHash);
    report.checks.push('external_reference succeeds and source SHA-256 is unchanged');
    await page.locator('.katex').first().waitFor();
    assert.ok(await page.locator('.katex').count() >= 4);
    assert.equal(await page.locator('.katex-error').count(), 0);
    await page.evaluate(() => document.fonts.ready);
    report.checks.push('Chinese Markdown, inline formulas, matrix, integral and cases render without KaTeX errors');
    await page.getByRole('button', {name:'用默认阅读器打开合成 PDF',exact:true}).click();
    await page.getByText('已向 Windows 提交打开请求；是否正确显示需查看阅读器。', {exact:true}).waitFor();
    await settle(page);
    await page.locator('[data-testid="stDataFrame"] canvas').first().waitFor();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    report.checks.push('Windows accepted the default-reader launch request (visual display requires manual acceptance)');
    await page.screenshot({path:path.join(sandbox,'browser-smoke.png'),fullPage:true});
    assert.deepEqual(report.externalRequests, []);
    assert.deepEqual(report.pageErrors, []);
    assert.deepEqual(report.consoleErrors, []);
    report.checks.push('fresh browser profile: zero non-loopback requests and zero browser errors in tested flows');
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.error = error.stack;
    throw error;
  } finally {
    report.finishedAt = new Date().toISOString();
    await fs.writeFile(path.join(sandbox,'browser-smoke.json'), JSON.stringify(report,null,2),'utf8');
    await context.close();
    console.log(JSON.stringify(report,null,2));
  }
})().catch(() => {process.exitCode=1;});
