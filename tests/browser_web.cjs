// Optional browser regression: node tests/browser_web.cjs (requires Playwright).
// All API responses are mocked; no ODPS calls or production data mutations.
const {chromium} = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.BROWSER_CHANNEL ? {channel:process.env.BROWSER_CHANNEL} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1374,height:1150}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let hold = false, release, started, estimates = 0;
    let releaseJob, jobStarted;
    await page.route('http://preview.local/**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/') return route.fulfill({contentType:'text/html', body:fs.readFileSync('app/web/index.html','utf8')});
      if (path === '/assets/date-range-picker.js') return route.fulfill({contentType:'application/javascript', body:fs.readFileSync('app/web/date-range-picker.js','utf8')});
      if (path === '/api/v1/auth/me') return route.fulfill({json:{username:'preview',role:'superadmin',is_superadmin:true}});
      if (path === '/api/v1/query-estimates') {
        const body = route.request().postDataJSON();
        estimates++;
        if (hold) { started(); await new Promise(resolve => {release = resolve;}); }
        return route.fulfill({json:{log_type:body.log_type,event_code:'70081134',partition_start:body.start_date.replaceAll('-',''),partition_end:body.end_date.replaceAll('-',''),input_size_bytes:2147483648,input_size_gib:2,complexity:1,udf_count:0,price_per_gib_cny:.3,estimated_amount_cny:.6,estimate_token:'mock',expires_at:new Date(Date.now()+600000).toISOString()}});
      }
      if (path === '/api/v1/query-requests') {
        assert.equal(route.request().postDataJSON().log_type,'web');
        return route.fulfill({json:{id:'mock-job',log_type:'web'}});
      }
      if (path === '/api/v1/jobs/mock-job') {
        jobStarted();
        await new Promise(resolve => {releaseJob=resolve;});
        return route.fulfill({json:{id:'mock-job',log_type:'web',event_code:'70081134',status:'succeeded',detail_row_count:2,aggregation:[{event_date:'20260908',pv:2,uv:1}]}});
      }
      if (path.endsWith('/download')) return route.fulfill({status:200,headers:{'Content-Disposition':'attachment; filename=mock.xlsx'},body:'mock-download'});
      return route.fulfill({json:{id:'preview-visit'}});
    });
    await page.goto('http://preview.local/');
    await page.locator('#appShell').waitFor({state:'visible'});
    await page.evaluate(() => document.fonts.ready);
    await page.locator('[data-log-type="web"]').click();
    await page.locator('#question').fill('帮我查询 70081134 的数据');
    assert.equal(await page.locator('#question').inputValue(),'帮我查询70081134的数据');
    fs.mkdirSync('outputs/v004-preview',{recursive:true});
    await page.screenshot({path:'outputs/v004-preview/desktop.png',fullPage:true,animations:'disabled'});
    await page.locator('#estimateButton').click();
    await page.waitForFunction(() => !document.querySelector('#submitButton').disabled);
    assert.match(await page.locator('#eventCode').textContent(),/WEB端/);
    await page.screenshot({path:'outputs/v004-preview/cost.png',fullPage:true,animations:'disabled'});
    await page.locator('[data-log-type="client"]').click();
    assert.equal(await page.locator('#submitButton').isDisabled(),true);
    await page.locator('.recent-use').first().click();
    assert.equal(await page.locator('[data-log-type="web"]').getAttribute('aria-pressed'),'true');
    hold = true;
    const arrived = new Promise(resolve => {started = resolve;});
    await page.locator('#estimateButton').click();
    await arrived;
    await page.locator('[data-log-type="client"]').click();
    release();
    await page.waitForFunction(() => !document.querySelector('#estimateButton').disabled);
    assert.equal(await page.locator('#submitButton').isDisabled(),true);
    await page.locator('[data-log-type="web"]').click();
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'outputs/v004-preview/mobile.png',fullPage:true,animations:'disabled'});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),true);
    hold = false;
    await page.locator('#estimateButton').click();
    await page.waitForFunction(() => !document.querySelector('#submitButton').disabled);
    const jobArrived = new Promise(resolve => {jobStarted=resolve;});
    await page.locator('#submitButton').click();
    await jobArrived;
    assert.equal(await page.locator('[data-log-type="client"]').isDisabled(),true);
    releaseJob();
    await page.waitForFunction(() => document.querySelector('#result').textContent.includes('查询完成'));
    assert.equal(await page.locator('[data-log-type="client"]').isDisabled(),false);
    assert.equal(await page.locator('#analyticsPanel').isVisible(),true);
    assert.deepEqual(errors,[]);
    assert.equal(estimates,3);
    console.log('PASS: desktop/mobile, whitespace, WEB estimate, type invalidation, history restore, stale response rejection; zero browser errors.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode=1;});
