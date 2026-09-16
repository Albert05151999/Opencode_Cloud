import { test, expect } from '../../../admin_web/frontend/node_modules/@playwright/test/index.mjs';
const model = {id:'test', name:'Test', enabled:true, provider:'openai-compatible', upstream_model:'test', base_url:'https://example.invalid', api_key:'', parameters:{}};
const catalog = {revision:1,models:{test:model},agents:{},resources:{},jobs:{},gateway_versions:[]};
test.beforeEach(async ({page}) => {
  await page.route('**/remote/**', r => r.fulfill({json:{}}));
  await page.route('**/local/bootstrap', r => r.fulfill({json:{url:'http://example.invalid:18080',csrf:'test',credential_configured:true,credential_persistence_available:false}}));
  await page.route('**/remote/cloud/admin/catalog?*', r => r.fulfill({json:catalog}));
  await page.route('**/remote/cloud/capabilities', r => r.fulfill({json:{sandbox_operations:true,resource_transfer:true,load_testing:true}}));
  await page.route('**/remote/cloud/admin/recovery-policy', r => r.fulfill({json:{enabled:true,backoff_seconds:[30,60,120],failure_threshold:3,max_attempts:3,window_seconds:900,stable_seconds:300}}));
  await page.route('**/remote/cloud/agents', r => r.fulfill({json:[]}));
  await page.route('**/remote/cloud/admin/sandboxes?*', r => r.fulfill({json:{items:[],total:0}}));
});
test('tabs survive refresh and browser history; connection shortcut opens settings',async({page})=>{
  await page.goto('/admin?tab=connection');await expect(page.getByRole('heading',{name:'服务器连接'})).toBeVisible();
  await expect(page.getByText('保存到 Windows Credential Manager')).toHaveCount(0);
  await page.getByRole('button',{name:'沙箱',exact:true}).click();await page.reload();await expect(page.getByRole('heading',{name:'沙箱运维 · 0'})).toBeVisible();
  await page.goBack();await expect(page.getByRole('heading',{name:'服务器连接'})).toBeVisible();
  await page.getByRole('button',{name:'模型',exact:true}).click();await page.getByRole('button',{name:'服务器连接设置'}).click();await expect(page.getByRole('heading',{name:'服务器连接'})).toBeVisible();
});
test('dirty model form confirms cancellation and traps keyboard focus',async({page})=>{
  await page.goto('/admin');await page.getByRole('button',{name:'新建',exact:true}).click();await page.getByLabel('稳定 ID',{exact:true}).fill('unsaved');
  page.on('dialog', d=>d.dismiss());await page.getByRole('button',{name:'取消',exact:true}).click();await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByLabel('稳定 ID',{exact:true})).toHaveValue('unsaved');
  await page.getByRole('button',{name:'保存到服务器'}).focus();await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'关闭编辑器'})).toBeFocused();
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toBeVisible();
});
test('capability check recovers after network failure',async({page})=>{
  let calls=0;await page.route('**/remote/cloud/capabilities',r=>++calls===1?r.abort():r.fulfill({json:{sandbox_operations:true}}));
  await page.goto('/admin?tab=sandboxes');await page.getByRole('button',{name:'重试检测'}).click();await expect(page.getByRole('heading',{name:'沙箱运维 · 0'})).toBeVisible();
});
test('empty filters show a valid range and can be cleared',async({page})=>{
  await page.goto('/admin?tab=sandboxes');await page.getByRole('textbox',{name:'搜索沙箱'}).fill('missing');await expect(page.getByText('0–0 / 0')).toBeVisible();
  await page.getByRole('button',{name:'清除筛选'}).click();await expect(page.getByRole('textbox',{name:'搜索沙箱'})).toHaveValue('');
});
test('recovery form rejects invalid intervals without writing and locks while saving',async({page})=>{
  let writes=0;await page.route('**/remote/cloud/admin/recovery-policy',async r=>{const v={enabled:true,backoff_seconds:[30],failure_threshold:3,max_attempts:3,window_seconds:900,stable_seconds:300};if(r.request().method()==='PUT'){writes++;await new Promise(resolve=>setTimeout(resolve,300));}await r.fulfill({json:v});});
  await page.goto('/admin?tab=sandboxes');await page.getByText('异常沙箱自动恢复设置',{exact:true}).click();await page.getByLabel('退避间隔（秒，逗号分隔）').fill('1,,2');await page.getByRole('button',{name:'保存策略'}).click();await expect(page.getByText('请填写 1–10 个整数间隔', {exact:false})).toBeVisible();expect(writes).toBe(0);
  await page.getByLabel('退避间隔（秒，逗号分隔）').fill('30，60');await page.getByRole('button',{name:'保存策略'}).click();await expect(page.getByRole('button',{name:'保存中…'})).toBeDisabled();await expect(page.getByText('恢复策略已保存')).toBeVisible();expect(writes).toBe(1);
});
test('structured validation errors name the invalid field and keep the connection editable',async({page})=>{
  await page.route('**/local/connection',r=>r.fulfill({status:422,json:{detail:[{loc:['body','url'],msg:'必须填写有效服务器地址'}]}}));
  await page.goto('/admin?tab=connection');await page.getByRole('button',{name:'保存连接',exact:true}).click();await expect(page.getByRole('alert')).toContainText('url：必须填写有效服务器地址');await expect(page.getByLabel('API 地址')).toHaveValue('http://example.invalid:18080');
});
test('model test failure is explicit and never displayed as a success',async({page})=>{
  await page.route('**/remote/cloud/admin/models/test/test',r=>r.fulfill({json:{ok:false,error:'上游凭据无效'}}));
  await page.goto('/admin');await page.getByRole('button',{name:'测试',exact:true}).click();await expect(page.getByText('连接测试失败',{exact:true})).toBeVisible();await expect(page.locator('.notice.success')).toHaveCount(0);
});
test('jobs show time, translated outcome, and details',async({page})=>{
  const j={id:'job1',kind:'agent.apply',target:'test-agent',status:'succeeded',checkpoint:'complete',created:1789477200,updated:1789477205};
  await page.route('**/remote/cloud/admin/jobs?*',r=>r.fulfill({json:{items:[j],total:1}}));await page.route('**/remote/cloud/admin/jobs/job1',r=>r.fulfill({json:j}));
  await page.goto('/admin?tab=jobs');await expect(page.getByText('发布 Agent · test-agent',{exact:true})).toBeVisible();await page.getByRole('button',{name:'查看详情'}).click();await expect(page.getByRole('region',{name:'任务详情'})).toContainText('执行阶段：完成');
});
test('a slow previous sandbox search cannot replace newer results',async({page})=>{
  let release: (()=>void) | undefined;
  await page.route('**/remote/cloud/admin/sandboxes?*',async r=>{
    const q=new URL(r.request().url()).searchParams.get('q');
    if(q==='old') await new Promise<void>(resolve=>{release=resolve});
    await r.fulfill({json:{items:q?[{sandbox_id:q,agent_id:'a',username:'test',status:'stopped'}]:[],total:q?1:0}});
  });
  await page.goto('/admin?tab=sandboxes');await page.getByLabel('搜索沙箱').fill('old');await expect.poll(()=>Boolean(release)).toBe(true);
  await page.getByLabel('搜索沙箱').fill('new');await expect(page.getByText('new',{exact:true})).toBeVisible();release!();await page.waitForTimeout(250);await expect(page.getByText('new',{exact:true})).toBeVisible();await expect(page.getByText('old',{exact:true})).toHaveCount(0);
});
test('creating a duplicate resource never overwrites its existing draft',async({page})=>{
  let writes=0;await page.route('**/remote/cloud/admin/catalog?*',r=>r.fulfill({json:{...catalog,resources:{existing:{id:'existing',kind:'mcp',name:'Existing',draft:{data:{type:'remote',url:'https://example.invalid/mcp'}},versions:[]}}}}));
  await page.route('**/remote/cloud/admin/resources/existing',r=>{writes++;return r.fulfill({json:{ok:true}})});
  await page.goto('/admin?tab=mcp');await page.getByRole('button',{name:'新建',exact:true}).click();await page.getByLabel('稳定 ID',{exact:true}).fill('existing');await page.getByLabel('名称（字母、数字、横线）').fill('overwrite');await page.getByLabel('服务 URL').fill('https://example.invalid/new');await page.getByRole('button',{name:'保存到服务器'}).click();await expect(page.getByRole('dialog')).toContainText('资源 ID 已存在');expect(writes).toBe(0);
});
test('permanent deletion waits for the job then refreshes the Agent list',async({page})=>{
  let deleted=false, polls=0;
  const agent={id:'delete-test',lifecycle:'archived',draft:{name:'Delete fixture',allowed_model_ids:[],bindings:[]},versions:[],active:0};
  await page.route('**/remote/cloud/admin/catalog?*',r=>r.fulfill({json:{...catalog,agents:deleted?{}:{'delete-test':agent}}}));
  await page.route('**/remote/cloud/admin/agents/delete-test/delete-preview',r=>r.fulfill({json:{sandboxes:[],sessions:0,files:0,bytes:0,private_resources:[],preview_id:'preview'}}));
  await page.route('**/remote/cloud/admin/agents/delete-test/delete',r=>r.fulfill({json:{job_id:'deleting'}}));
  await page.route('**/remote/cloud/admin/jobs/deleting',r=>{deleted=++polls>1;return r.fulfill({json:{id:'deleting',kind:'agent.delete',status:deleted?'succeeded':'running'}})});
  await page.goto('/admin?tab=agents');await page.getByLabel('显示归档与删除中 Agent').check();await page.getByRole('button',{name:'永久删除…'}).click();await page.getByLabel('确认删除 Agent ID').fill('delete-test');await page.getByRole('button',{name:'确认永久删除'}).click();await expect(page.getByRole('status')).toContainText('删除任务处理中');await expect(page.getByRole('heading',{name:'Delete fixture'})).toHaveCount(0);expect(polls).toBeGreaterThan(1);
});
test('job history loads only on entry or manual refresh and exports all records',async({page})=>{
 let reads=0;
 await page.clock.install();
 await page.route('**/remote/cloud/admin/jobs?*',r=>{reads++;expect(new URL(r.request().url()).searchParams.get('limit')).toBe('50');return r.fulfill({json:{items:[],total:0}})});
 await page.goto('/admin?tab=models');await page.clock.fastForward(15000);expect(reads).toBe(0);
 await page.getByRole('button',{name:'发布记录',exact:true}).click();await expect.poll(()=>reads).toBe(1);
 await page.clock.fastForward(15000);expect(reads).toBe(1);
 await page.getByRole('button',{name:'刷新任务'}).click();await expect.poll(()=>reads).toBe(2);
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'下载完整记录'}).click();await download;
 await page.getByRole('button',{name:'模型',exact:true}).click();await page.clock.fastForward(15000);expect(reads).toBe(2);
});

for(const kind of ['mcp','skill','hook']) test(`${kind} archive filter, restore and delete preserve explicit lifecycle`,async({page})=>{
 let archived=true,deleted=false;
 await page.route('**/remote/cloud/admin/catalog?*',r=>r.fulfill({json:{...catalog,resources:deleted?{}:{sample:{id:'sample',kind,name:'sample',archived,owner:null,draft:{data:{}},versions:[]}}}}));
 await page.route('**/remote/cloud/admin/resources/sample/restore',r=>{archived=false;return r.fulfill({json:{ok:true}})});
 await page.route('**/remote/cloud/admin/resources/sample/archive',r=>{archived=true;return r.fulfill({json:{ok:true}})});
 await page.route('**/remote/cloud/admin/resources/sample?*',r=>{expect(r.request().method()).toBe('DELETE');deleted=true;return r.fulfill({json:{ok:true}})});
 page.on('dialog',d=>d.accept());
 await page.goto('/admin?tab='+kind);
 await expect(page.getByRole('button',{name:'恢复',exact:true})).toHaveCount(0);
 await page.getByLabel(/显示归档与删除中/).check();
 await page.getByRole('button',{name:'恢复',exact:true}).click();await expect(page.getByRole('button',{name:'归档',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'归档',exact:true}).click();
 await page.getByRole('button',{name:'永久删除',exact:true}).click();
 await expect(page.getByRole('button',{name:'永久删除',exact:true})).toHaveCount(0);
});
