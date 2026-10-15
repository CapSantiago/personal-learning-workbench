// Real browser checks against a NEW synthetic workspace served on 8505.
// Usage: node upload_browser.cjs <bundled node_modules> <synthetic workspace root>
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const [modules, rootArgument] = process.argv.slice(2);
const {chromium} = require(path.join(modules, 'playwright'));
const root = path.resolve(rootArgument);
const project = path.resolve(__dirname, '..');
const relativeRoot = path.relative(path.join(project, '.sandbox', 'test-runs'), root);
assert.ok(relativeRoot && !relativeRoot.startsWith('..') && !path.isAbsolute(relativeRoot), 'Only a synthetic test-runs subdirectory is allowed');
const base = 'http://127.0.0.1:8505';
const out = path.join(root, 'evidence');
const report = {started: new Date().toISOString(), checks: [], external: [], errors: [], readerRequests: [], readerResponses: [], devices: ['Edge desktop', 'Edge tablet viewport, independent browser context; not physical iPad Safari']};
const snapshotProgram = String.raw`
import json, sqlite3, sys
from pathlib import Path
database = Path(sys.argv[1]); root = Path(sys.argv[2])
assert database.is_relative_to(root / 'datasets') and database.name == 'plw.sqlite3'
connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
connection.row_factory = sqlite3.Row
result = {name: [dict(row) for row in connection.execute('SELECT * FROM ' + name)]
          for name in ('materials', 'reading_editions', 'reading_progress', 'annotations')}
connection.close()
print(json.dumps(result, ensure_ascii=False))
`;
const idle = async p => {
  await p.waitForTimeout(250);
  await p.waitForFunction(() => document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state') === 'notRunning', undefined, {timeout: 180000});
  assert.equal(await p.getByTestId('stException').count(), 0, 'Streamlit exception');
};
const ready = async p => {await p.locator('.reader-root[data-ready="true"]').waitFor({timeout: 150000}); await idle(p);};
const details = (p, label) => p.locator('details').filter({has: p.locator('summary').getByText(label, {exact: true})}).first();
async function expand(p, label) {
  const d = details(p, label); await d.waitFor();
  if (!(await d.evaluate(e => e.open))) await d.locator(':scope > summary').click();
  return d;
}
async function select(p, label, value) {
  const input = p.getByLabel(label, {exact: true});
  await input.click(); await input.fill(value);
  await p.getByRole('option', {name: value, exact: true}).click(); await idle(p);
}
async function bookshelf(p, course) {
  const opener = p.getByTestId('stExpandSidebarButton');
  if (await opener.isVisible()) await opener.click();
  await p.getByTestId('stSidebar').getByRole('button', {name: '课程书架', exact: true}).click();
  await p.getByRole('heading', {name: '课程书架', exact: true}).waitFor(); await idle(p);
  await select(p, '选择课程', course);
}
async function submit(p, summary) {
  const d = await expand(p, '导入课件');
  await d.getByRole('button', {name: '导入所选课件', exact: true}).click();
  await idle(p);
  await d.getByText(summary, {exact: true}).waitFor({timeout: 180000});
  await idle(p);
}
async function clearAndChoose(p, files) {
  const d = await expand(p, '导入课件');
  const clear = d.getByRole('button', {name: '清空选择', exact: true});
  if (await clear.isEnabled()) {await clear.click(); await idle(p);}
  await d.locator('input[type="file"]').setInputFiles(files); await idle(p);
}
async function pageNumber(p, value) {
  await p.getByLabel('跳转页码', {exact: true}).fill(String(value));
  await p.locator('[data-cmd="jump"]').click();
  await p.locator(`.reader-root[data-page="${value}"][data-ready="true"]`).waitFor(); await ready(p);
}
async function contextFor(browser, options) {
  const context = await browser.newContext(options);
  await context.route('**/*', async route => {
    const requestUrl = new URL(route.request().url());
    if (requestUrl.pathname.startsWith('/plw-reader/')) report.readerRequests.push(requestUrl.href);
    if (requestUrl.origin === base) await route.continue();
    else {report.external.push(requestUrl.href); await route.abort();}
  });
  await context.routeWebSocket('**/*', socket => {
    const url = new URL(socket.url());
    if (url.hostname === '127.0.0.1' && url.port === '8505') socket.connectToServer();
    else {report.external.push(url.href); socket.close();}
  });
  context.on('page', p => {
    p.setDefaultTimeout(30000); p.on('pageerror', error => report.errors.push(error.message));
    p.on('response', response => {
      if (new URL(response.url()).pathname.startsWith('/plw-reader/')) report.readerResponses.push({url: response.url(), status: response.status()});
    });
  });
  return context;
}

(async () => {
  const setup = JSON.parse(await fs.readFile(path.join(out, 'setup.json'), 'utf8'));
  assert.equal(path.resolve(setup.root), root);
  const snapshot = () => JSON.parse(execFileSync(path.join(project, '.venv', 'Scripts', 'python.exe'),
    ['-X', 'utf8', '-B', '-c', snapshotProgram, setup.database, root], {encoding: 'utf8', windowsHide: true}));
  const courseMaterials = (data, course = setup.courses[0].id) => data.materials.filter(m => m.course_id === course && !m.deleted_at);
  const browser = await chromium.launch({channel: 'msedge', headless: true, args: ['--disable-background-networking', '--no-first-run']});
  const desktop = await contextFor(browser, {viewport: {width: 1440, height: 1000}});
  const p = await desktop.newPage();
  try {
    assert.equal(snapshot().materials.length, 0, 'Use a new empty seed for every acceptance run');
    await p.goto(base); await p.getByRole('heading', {name: '今日学习', exact: true}).waitFor(); await idle(p);
    await bookshelf(p, setup.courses[0].name);
    assert.equal(await p.getByLabel('文件绝对路径', {exact: true}).count(), 0);
    const upload = await expand(p, '导入课件');
    assert.equal(await upload.locator('input[type="file"]').getAttribute('multiple'), '');
    assert.equal(await upload.getByRole('button', {name: '导入所选课件', exact: true}).isDisabled(), true);
    // The browser emits this only when the actual uploader button invokes the native picker.
    const [chooser] = await Promise.all([p.waitForEvent('filechooser'),
      upload.getByRole('button', {name: /Upload|Browse files|浏览文件|选择文件/}).click()]);
    assert.equal(chooser.isMultiple(), true);
    await chooser.setFiles([setup.files.native.path, setup.files.rotated.path, setup.files.damaged.path]);
    await idle(p);
    await upload.getByText(/已选 3 份/).waitFor();
    await p.screenshot({path: path.join(out, 'upload-file-selection.png'), fullPage: true});
    report.checks.push('Native file chooser supports multiple files; bookshelf has no absolute-path input');

    await submit(p, '本批 3 份：2 份可阅读，1 份已保存待处理，0 份未导入。');
    const initial = snapshot();
    assert.equal(courseMaterials(initial).length, 3); assert.equal(initial.reading_editions.length, 2);
    for (const key of ['native', 'rotated', 'damaged']) {
      const input = setup.files[key];
      const material = courseMaterials(initial).find(m => m.baseline_sha256 === input.sha256);
      assert.ok(material, 'Missing uploaded input ' + key); assert.equal(material.storage_mode, 'managed_copy');
      assert.equal(material.import_state, 'ready'); assert.equal(material.reference_path, null);
      const payload = await fs.readFile(path.join(path.dirname(setup.database), material.managed_relpath));
      assert.equal(crypto.createHash('sha256').update(payload).digest('hex'), input.sha256);
      const editions = initial.reading_editions.filter(e => e.material_id === material.id);
      assert.equal(editions.length, key === 'damaged' ? 0 : 1);
    }
    await p.screenshot({path: path.join(out, 'upload-mixed-results.png'), fullPage: true});
    report.checks.push('Two PDFs have verified managed copies and reading editions; malformed PDF is retained without preventing valid imports');

    await submit(p, '本批 3 份：2 份可阅读，1 份已保存待处理，0 份未导入。');
    let data = snapshot();
    assert.deepEqual(data.materials.map(m => m.id).sort(), initial.materials.map(m => m.id).sort());
    assert.deepEqual(data.reading_editions.map(e => e.id).sort(), initial.reading_editions.map(e => e.id).sort());
    report.checks.push('Retrying the same batch keeps material and reading-edition identities');
    await clearAndChoose(p, [setup.files.native.path]);
    await submit(p, '本批 1 份：1 份可阅读，0 份已保存待处理，0 份未导入。');
    data = snapshot(); assert.equal(data.materials.length, 3); assert.equal(data.reading_editions.length, 2);
    report.checks.push('Selecting the same file in a fresh upload selection does not duplicate it');

    await clearAndChoose(p, [setup.files.changed_name.path]);
    await submit(p, '本批 1 份：1 份可阅读，0 份已保存待处理，0 份未导入。');
    data = snapshot();
    assert.equal(data.materials.length, 4); assert.equal(data.reading_editions.length, 3);
    const sameNames = courseMaterials(data).filter(m => m.name === setup.files.native.name);
    assert.equal(sameNames.length, 2); assert.equal(new Set(sameNames.map(m => m.baseline_sha256)).size, 2);
    report.checks.push('Different contents with the same filename remain separate, preserving both inputs');

    await clearAndChoose(p, [setup.files.presentation.path]);
    await submit(p, '本批 1 份：1 份可阅读，0 份已保存待处理，0 份未导入。');
    data = snapshot();
    const ppt = courseMaterials(data).find(m => m.baseline_sha256 === setup.files.presentation.sha256);
    const pptEdition = data.reading_editions.find(e => e.material_id === ppt.id);
    assert.ok(pptEdition && pptEdition.page_count > 0); assert.equal(data.materials.length, 5);
    await (await expand(p, '导入课件')).getByRole('button', {name: '阅读刚导入的课件', exact: true}).click();
    await p.locator(`.reader-root[data-doc="${pptEdition.id}"][data-ready="true"]`).waitFor({timeout: 150000}); await ready(p);
    report.checks.push('Uploaded PPTX automatically becomes a readable static PDF and opens from the result action');

    await select(p, '选择课件', setup.files.rotated.name); await ready(p); await pageNumber(p, 2);
    const sharedDoc = await p.locator('.reader-root').getAttribute('data-doc');
    await p.locator('[data-cmd="rectangle"]').click();
    const canvas = p.locator('canvas.marks'); await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox(); assert.ok(box && box.width > 100 && box.height > 100);
    await p.mouse.move(box.x + box.width * .2, box.y + Math.min(80, box.height * .2));
    await p.mouse.down(); await p.mouse.move(box.x + box.width * .5, box.y + Math.min(150, box.height * .5), {steps: 8}); await p.mouse.up();
    await p.locator('.reader-root[data-marks="1"][data-ready="true"]').waitFor(); await ready(p);
    const marks = snapshot().annotations.filter(a => a.edition_id === sharedDoc && !a.deleted_at);
    assert.equal(marks.length, 1); assert.equal(marks[0].page, 2);

    await select(p, '选择课程', setup.courses[1].name);
    assert.equal(await p.getByLabel('选择课件', {exact: true}).count(), 0);
    await clearAndChoose(p, [setup.files.native.path]);
    await submit(p, '本批 1 份：1 份可阅读，0 份已保存待处理，0 份未导入。');
    data = snapshot(); assert.equal(courseMaterials(data).length, 5);
    assert.equal(courseMaterials(data, setup.courses[1].id).length, 1);
    assert.notEqual(courseMaterials(data, setup.courses[1].id)[0].id, courseMaterials(initial)[0].id);
    report.checks.push('Import selection is scoped to the chosen course and the same source can belong to a second course');

    const tablet = await contextFor(browser, {viewport: {width: 1024, height: 1366}, hasTouch: true, isMobile: true, deviceScaleFactor: 2});
    const t = await tablet.newPage(); await t.goto(base);
    await t.getByRole('heading', {name: '今日学习', exact: true}).waitFor(); await idle(t);
    await bookshelf(t, setup.courses[0].name); await select(t, '选择课件', setup.files.rotated.name);
    await t.locator(`.reader-root[data-doc="${sharedDoc}"][data-page="2"][data-marks="1"][data-ready="true"]`).waitFor(); await ready(t);
    const width = await t.evaluate(() => ({viewport: innerWidth, document: document.documentElement.scrollWidth}));
    assert.ok(width.document <= width.viewport + 2, JSON.stringify(width));
    await t.screenshot({path: path.join(out, 'upload-tablet-reading.png'), fullPage: true});
    const tabletUpload = await expand(t, '导入课件');
    assert.equal(await tabletUpload.locator('input[type="file"]').count(), 1);
    assert.equal(await tabletUpload.getByRole('button', {name: '导入所选课件', exact: true}).isDisabled(), true);
    await tablet.close();
    report.checks.push('Independent tablet-size browser opens the stored courseware, saved page and mark without access to the desktop source path');

    assert.ok(report.readerRequests.length > 0, 'Reader must request same-origin assets');
    for (const address of report.readerRequests) assert.equal(new URL(address).origin, base);
    assert.ok(report.readerResponses.some(r => [200, 206].includes(r.status)), 'Reader responses should succeed');
    assert.ok(report.readerResponses.every(r => r.status < 400), JSON.stringify(report.readerResponses));
    assert.equal(report.external.length, 0); assert.equal(report.errors.length, 0);
    for (const source of Object.values(setup.files)) assert.equal(crypto.createHash('sha256').update(await fs.readFile(source.path)).digest('hex'), source.sha256);
    report.checks.push('Reader assets use the page origin, no external requests occur, and all synthetic source files remain unchanged');
    report.passed = true;
  } catch (error) {
    report.passed = false; report.failure = error.stack;
    report.body = (await p.locator('body').innerText()).slice(-7000);
    await p.screenshot({path: path.join(out, 'upload-failure.png'), fullPage: true});
    process.exitCode = 1;
  } finally {
    report.finished = new Date().toISOString();
    await fs.writeFile(path.join(out, 'upload-browser.json'), JSON.stringify(report, null, 2));
    await browser.close(); console.log(JSON.stringify(report, null, 2));
  }
})();
