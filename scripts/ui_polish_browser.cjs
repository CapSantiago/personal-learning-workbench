// Real UI acceptance; run only against the dedicated synthetic service on 8505.
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const [modules, root] = process.argv.slice(2);
const {chromium} = require(path.join(modules, 'playwright'));
const out = path.join(root, 'evidence');
const report = {started: new Date().toISOString(), checks: [], external: [], errors: []};
const common = ['今日学习', '课程书架', '任务管理', '笔记'];
const management = ['章节与知识点', '课程管理', '学期管理', '资料管理', '数据与备份', '使用说明'];
const idle = async p => {
  await p.waitForTimeout(250);
  await p.waitForFunction(() => document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state') === 'notRunning');
  assert.equal(await p.getByTestId('stException').count(), 0, 'Streamlit raised an exception');
};
const ready = async p => {await p.locator('.reader-root[data-ready="true"]').waitFor({timeout: 120000}); await idle(p);};
const details = (p, label) => p.locator('details').filter({has: p.locator('summary').getByText(label, {exact: true})}).first();
async function expand(p, label) {
  const d = details(p, label);
  await d.waitFor();
  if (!(await d.evaluate(e => e.open))) await d.locator(':scope > summary').click();
  return d;
}
async function sidebar(p) {
  const opener = p.getByTestId('stExpandSidebarButton');
  if (await opener.isVisible()) await opener.click();
  return p.getByTestId('stSidebar');
}
async function nav(p, label) {
  const side = await sidebar(p);
  if (management.includes(label)) await expand(p, '课程与设置');
  await side.getByRole('button', {name: label, exact: true}).click();
  await p.getByRole('heading', {name: label, exact: true}).waitFor();
  await idle(p);
}
async function select(p, label, value) {
  const input = p.getByLabel(label, {exact: true});
  await input.click();
  await input.fill(value);
  await p.getByRole('option', {name: value, exact: true}).click();
  await idle(p);
}
async function prohibitExternal(context) {
  const local = value => ['127.0.0.1', 'localhost', '[::1]'].includes(new URL(value).hostname);
  await context.route('**/*', async r => {
    if (local(r.request().url())) await r.continue();
    else {report.external.push(r.request().url()); await r.abort();}
  });
  await context.routeWebSocket('**/*', ws => {
    if (local(ws.url())) ws.connectToServer();
    else {report.external.push(ws.url()); ws.close();}
  });
}
async function noOverflow(p, label) {
  const size = await p.evaluate(() => {
    const main = document.querySelector('[data-testid="stMain"]');
    return {viewport: innerWidth, document: document.documentElement.scrollWidth,
      mainWidth: main?.clientWidth, mainScroll: main?.scrollWidth};
  });
  assert.ok(size.document <= size.viewport + 2, label + ': page overflow ' + JSON.stringify(size));
  assert.ok(!size.mainWidth || size.mainScroll <= size.mainWidth + 2, label + ': main overflow ' + JSON.stringify(size));
  return size;
}

(async () => {
  await fs.mkdir(out, {recursive: true});
  const setup = JSON.parse(await fs.readFile(path.join(out, 'setup.json'), 'utf8'));
  const browser = await chromium.launch({channel: 'msedge', headless: true, args: ['--disable-background-networking', '--no-first-run']});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await prohibitExternal(context);
  const p = await context.newPage();
  p.on('pageerror', e => report.errors.push(e.message));
  p.setDefaultTimeout(30000);
  try {
    await p.goto('http://127.0.0.1:8505/');
    await p.getByRole('heading', {name: '今日学习', exact: true}).waitFor();
    await idle(p);
    const side = p.getByTestId('stSidebar');
    for (const label of common) assert.equal(await side.getByRole('button', {name: label, exact: true}).isVisible(), true);
    assert.equal(await details(p, '课程与设置').evaluate(e => e.open), false);
    for (const label of management) assert.equal(await side.getByRole('button', {name: label, exact: true}).isVisible(), false);
    const homeText = await p.locator('body').innerText();
    assert.ok(!homeText.includes(root) && !homeText.includes('E:\\PLW-Data'), 'Workspace paths should not appear on the learning home');
    await p.screenshot({path: path.join(out, 'ui-home-desktop.png'), fullPage: true});
    report.checks.push('four everyday navigation entries, collapsed management, no workspace path on home');

    // First establish a known reading position, then verify the homepage route
    // passes both the chosen material and its immutable reading edition.
    await nav(p, '课程书架');
    await select(p, '选择课程', '自动控制原理');
    await ready(p);
    const name = '原生 PDF 中文课件.pdf', edition = setup.editions[name];
    assert.ok(edition, 'setup.json must contain the native PDF edition');
    await select(p, '选择课件', name);
    await p.locator(`.reader-root[data-doc="${edition}"][data-ready="true"]`).waitFor();
    await p.getByLabel('跳转页码', {exact: true}).fill('2');
    await p.locator('[data-cmd="jump"]').click();
    await p.locator(`.reader-root[data-doc="${edition}"][data-page="2"][data-ready="true"]`).waitFor();
    await ready(p);
    await nav(p, '今日学习');
    await p.locator('.st-key-resume_' + edition).getByRole('button', {name: '继续阅读', exact: true}).click();
    await p.locator(`.reader-root[data-doc="${edition}"][data-page="2"][data-ready="true"]`).waitFor();
    await ready(p);
    report.checks.push('homepage resume opens the exact material edition and saved page');

    assert.equal(await details(p, '书签与批注').evaluate(e => e.open), false);
    assert.equal(await p.getByLabel('标记内容（可写公式和 Markdown）', {exact: true}).isVisible(), false);
    await p.screenshot({path: path.join(out, 'ui-bookshelf-desktop.png'), fullPage: true});
    await expand(p, '书签与批注');
    const mark = '界面验收：复习闭环反馈 ' + Date.now();
    await p.getByLabel('标记内容（可写公式和 Markdown）', {exact: true}).fill(mark);
    await p.getByRole('button', {name: '保存标记', exact: true}).click();
    await ready(p);
    await expand(p, '书签与批注');
    await p.locator('summary').filter({hasText: mark}).waitFor();
    report.checks.push('annotation panel starts collapsed and still saves a text mark');

    await nav(p, '任务管理');
    await p.getByTestId('stDataFrame').waitFor();
    assert.equal(await details(p, '添加新任务').evaluate(e => e.open), false);
    assert.equal(await p.getByLabel('任务标题', {exact: true}).isVisible(), false);
    await p.screenshot({path: path.join(out, 'ui-tasks-desktop.png'), fullPage: true});
    await expand(p, '添加新任务');
    const taskTitle = '界面验收：整理本周课件 ' + Date.now();
    await p.getByLabel('任务标题', {exact: true}).fill(taskTitle);
    await p.getByRole('button', {name: '保存任务', exact: true}).click();
    await idle(p);
    await select(p, '编辑任务', '待开始 · ' + taskTitle);
    assert.equal(await p.getByLabel('任务标题', {exact: true}).inputValue(), taskTitle);
    assert.equal(await details(p, '编辑任务详情').evaluate(e => e.open), true);
    await p.getByTestId('stDataFrame').waitFor();
    report.checks.push('task list remains visible, new form is collapsed, saving creates a selectable task');

    await nav(p, '笔记');
    await p.getByRole('tab', {name: '编辑', exact: true}).click();
    const noteTitle = '界面验收：控制公式 ' + Date.now();
    await p.getByLabel('笔记标题', {exact: true}).fill(noteTitle);
    await p.getByLabel('Markdown 正文', {exact: true}).fill('# 闭环控制\n\n记录学习要点，行内公式 $x^2$。\n\n$$G(s)=\\frac{1}{s+1}$$');
    await p.getByRole('button', {name: '保存笔记', exact: true}).click();
    await idle(p);
    await select(p, '选择笔记', noteTitle);
    await p.getByRole('tab', {name: '阅读预览', exact: true}).click();
    await p.getByRole('tabpanel').filter({visible: true}).locator('.katex').first().waitFor();
    assert.equal(await p.getByLabel('Markdown 正文', {exact: true}).isVisible(), false);
    await p.screenshot({path: path.join(out, 'ui-notes-desktop.png'), fullPage: true});
    await p.getByRole('tab', {name: '编辑', exact: true}).click();
    assert.match(await p.getByLabel('Markdown 正文', {exact: true}).inputValue(), /G\(s\)/);
    report.checks.push('notes save successfully and switch between editing and rendered formula preview');

    await nav(p, '课程管理');
    assert.equal(await details(p, '编辑课程').evaluate(e => e.open), false);
    assert.equal(await details(p, '新建课程').evaluate(e => e.open), false);
    assert.equal(await details(p, '课程与设置').evaluate(e => e.open), true);
    for (const label of ['学期管理', '资料管理', '章节与知识点', '数据与备份', '使用说明']) await nav(p, label);
    report.checks.push('course editing stays collapsed and every management page remains accessible');

    await nav(p, '今日学习');
    await p.setViewportSize({width: 390, height: 844});
    await p.waitForTimeout(500); // Let Streamlit's responsive sidebar finish collapsing.
    await idle(p);
    const close = p.getByTestId('stSidebarCollapseButton');
    if (await p.getByTestId('stSidebar').getAttribute('aria-expanded') === 'true') await close.getByRole('button').click();
    await p.getByTestId('stExpandSidebarButton').waitFor({state: 'visible'});
    report.mobileHome = await noOverflow(p, 'mobile home');
    await p.screenshot({path: path.join(out, 'ui-home-mobile.png'), fullPage: true});
    await p.getByTestId('stExpandSidebarButton').click();
    await p.getByTestId('stSidebar').getByRole('button', {name: '任务管理', exact: true}).click();
    await p.getByRole('heading', {name: '任务管理', exact: true}).waitFor();
    await idle(p);
    if (await p.getByTestId('stSidebar').getAttribute('aria-expanded') === 'true') await close.getByRole('button').click();
    report.mobileTasks = await noOverflow(p, 'mobile tasks');
    await p.screenshot({path: path.join(out, 'ui-tasks-mobile.png'), fullPage: true});
    report.checks.push('390px mobile layout avoids page overflow and sidebar menu supports navigation');

    assert.equal(report.external.length, 0, 'Unexpected external request');
    assert.equal(report.errors.length, 0, 'Browser page error');
    report.passed = true;
  } catch (error) {
    report.passed = false;
    report.failure = error.stack;
    report.body = (await p.locator('body').innerText()).slice(-9000);
    await p.screenshot({path: path.join(out, 'ui-polish-failure.png'), fullPage: true});
    throw error;
  } finally {
    report.finished = new Date().toISOString();
    await fs.writeFile(path.join(out, 'ui-polish-browser.json'), JSON.stringify(report, null, 2));
    await browser.close();
    console.log(JSON.stringify(report, null, 2));
  }
})();

