const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');

(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
  try{
    const requests=[];
    const page=await browser.newPage({viewport:{width:1400,height:900}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.route('http://preview.local/**',route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/admin/usage')return route.fulfill({contentType:'text/html',body:fs.readFileSync('app/web/admin.html','utf8')});
      if(url.pathname==='/assets/date-range-picker.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('app/web/date-range-picker.js','utf8')});
      if(url.pathname==='/api/v1/admin/queries/test-job/sql')return route.fulfill({json:{detail_sql:'SELECT * FROM detail WHERE cid_parm = \'170035\';',aggregation_sql:'SELECT dt, COUNT(*) AS pv FROM detail GROUP BY dt;'}});
      if(url.pathname==='/api/v1/admin/usage'){
        requests.push(url.searchParams.get('query_limit'));
        return route.fulfill({json:{generated_at:new Date().toISOString(),daily_user_limit_cny:10,
          users:[{username:'member01',role:'member',active_days:2,page_views:3,query_count:4,stay_seconds:60,cost_estimate_count:5,export_count:2,consumed_amount_cny:1.2,last_access_at:new Date().toISOString()}],
          recent_visits:[],recent_queries:[{job_id:'test-job',username:'member01',created_at:new Date().toISOString(),status:'succeeded',log_type:'client',event_codes:['170035','90056'],partition_start:'20261101',partition_end:'20261102',systems:['ios'],version_mode:'greater_equal',versions:['16.4.1'],new_users:[1],value_fields:['value1','value2'],value_filters:[{field:'value1',logic:'and',connectors:['or'],conditions:[{operator:'ge',target:'100'},{operator:'lt',target:'200'}]},{field:'value2',conditions:[{operator:'contains',target:'abc'}]}]}]}});
      }
      return route.fulfill({status:404,body:'not found'});
    });
    await page.goto('http://preview.local/admin/usage');
    await page.locator('#queryCount').getByText('4').waitFor();
    assert.equal(await page.locator('[data-metric="stay_seconds"]').count(),0);
    assert.equal(await page.locator('#queryRecords details').count(),1);
    assert.equal(await page.locator('#userRows td').nth(4).textContent(),'4');
    await page.locator('[data-metric="query_count"]').click();
    assert.match(await page.locator('#waterfall').textContent(),/4 次/);
    await page.locator('#queryRecords summary').click();
    await page.locator('#queryRecords pre').first().waitFor();
    assert.match(await page.locator('#queryRecords').textContent(),/大于等于 16\.4\.1/);
    assert.match(await page.locator('#queryRecords').textContent(),/value1（大于等于 100 或 小于 200） 或 value2（包含 abc）/);
    assert.match(await page.locator('#queryRecords pre').first().textContent(),/SELECT \*/);
    await Promise.all([
      page.waitForResponse(response=>response.url().includes('query_limit=1000')),
      page.locator('#queryLimit').selectOption('1000'),
    ]);
    assert.equal(requests.at(-1),'1000');
    await page.locator('#queryRecords summary').click();
    fs.mkdirSync('outputs/v017-preview',{recursive:true});
    await page.screenshot({path:'outputs/v017-preview/admin-desktop.png',fullPage:true,animations:'disabled'});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'outputs/v017-preview/admin-mobile.png',fullPage:true,animations:'disabled'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    assert.deepEqual(errors,[]);
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
