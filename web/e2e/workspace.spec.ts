import{test,expect}from'@playwright/test';
const model={id:'coding-fast',name:'Coding Fast',provider:'legacy',upstream_model:'coding-fast',legacy:true,enabled:true};
const draft={name:'Code Agent',description:'你的云端代码助手',enabled:true,instructions:'Help with code.',allowed_model_ids:['coding-fast'],default_model_id:'coding-fast',small_model_id:null,bindings:[]};
const catalog={revision:1,models:{'coding-fast':model},agents:{'agent-code':{id:'agent-code',draft,active:1,versions:[{version:1,config:draft}]}},resources:{},jobs:{},gateway_versions:[]};
test.beforeEach(async({page})=>{
 await page.addInitScript(()=>{const native=window.fetch.bind(window);window.fetch=async(input,init)=>{if(input==='/remote/event'){const stream=new ReadableStream({start(c){(window as any).__events=c;c.enqueue(new TextEncoder().encode('data: {"type":"server.connected","properties":{}}\n\n'));}});return new Response(stream,{headers:{'content-type':'text/event-stream'}})}return native(input,init)};});
 await page.route('**/remote/**',async route=>{const url=new URL(route.request().url()),p=url.pathname.replace('/remote','');let data:any={};
 if(p==='/cloud/agents')data=[{id:'agent-code',version:1,...draft}];else if(p==='/cloud/models')data=[model];else if(p==='/cloud/admin/catalog')data=catalog;else if(p==='/session'&&route.request().method()==='GET')data=[];else if(p==='/session'&&route.request().method()==='POST')data={id:'ses_browser'};else if(p.endsWith('/message'))data=[];else if(p==='/question'||p==='/permission')data=[];else data={ok:true};
 await route.fulfill({json:data});});
});
test('chat is usable and submits a prompt once',async({page})=>{
 let submissions=0;page.on('request',r=>{if(r.url().endsWith('/prompt_async'))submissions++});
 await page.goto('/chat');await expect(page.getByText('让想法，在云端发生。')).toBeVisible();
 await expect(page.getByLabel('选择模型')).toHaveValue('coding-fast');
 await page.screenshot({path:'../artifacts/web/chat-desktop.png',fullPage:true});
 await page.getByLabel('消息',{exact:true}).fill('Calculate 1 + 1');await page.getByTitle('发送',{exact:true}).click();
 await expect.poll(()=>submissions).toBe(1);
 await page.evaluate(()=>{const c=(window as any).__events;for(const event of [
 {type:'message.updated',properties:{info:{id:'msg_a',sessionID:'ses_browser',role:'assistant'}}},
 {type:'message.part.updated',properties:{part:{id:'p',messageID:'msg_a',sessionID:'ses_browser',type:'text',text:'The answer is **2**.'}}}
 ])c.enqueue(new TextEncoder().encode('data: '+JSON.stringify(event)+'\n\n'));});
 await expect(page.getByText('The answer is')).toBeVisible();expect(submissions).toBe(1);
});
test('admin saves MCP through the API and preserves draft semantics',async({page})=>{
 let body:any;await page.route('**/remote/cloud/admin/resources/test-mcp',async route=>{body=route.request().postDataJSON();await route.fulfill({json:{ok:true}})});
 await page.goto('/admin');await page.getByRole('button',{name:'MCP',exact:true}).click();await page.getByRole('button',{name:'新建',exact:true}).click();
 await page.getByLabel('稳定 ID').fill('test-mcp');await page.getByLabel('名称（字母、数字、横线）').fill('test-mcp');await page.getByLabel('服务 URL').fill('https://mcp.example/api');
 await page.screenshot({path:'../artifacts/web/mcp-editor.png',fullPage:true});
 await page.getByRole('button',{name:'保存到服务器'}).click();await expect(page.getByText('草稿已保存到服务器；发布后才生效')).toBeVisible();
 expect(body.resource.data.oauth).toBe(false);expect(body.resource.owner).toBe(null);
});
test('Agent editor exposes explicit model selection and mobile layout',async({page})=>{
 await page.goto('/admin');await page.getByRole('button',{name:'Agents',exact:true}).click();await page.getByRole('button',{name:'配置 Agent'}).click();
 await expect(page.getByText('选择可用模型')).toBeVisible();await expect(page.getByLabel('默认模型',{exact:true})).toHaveValue('coding-fast');
 await page.screenshot({path:'../artifacts/web/agent-editor.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('/chat');await expect(page.getByLabel('消息',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.screenshot({path:'../artifacts/web/chat-mobile.png',fullPage:true});
 await page.getByRole('button',{name:'会话列表',exact:true}).click();await expect(page.getByRole('button',{name:'新对话',exact:true})).toBeVisible();
});

test('refresh restores the selected session without submitting again',async({page})=>{
 let submissions=0;page.on('request',r=>{if(r.url().endsWith('/prompt_async'))submissions++});
 await page.addInitScript(()=>localStorage.setItem('session:agent-code:local-demo','ses_saved'));
 await page.route('**/remote/session/ses_saved/message',r=>r.fulfill({json:[{info:{id:'msg_saved',role:'assistant',sessionID:'ses_saved'},parts:[{id:'p_saved',type:'text',text:'Saved server history'}]}]}));
 await page.route('**/remote/session/status',r=>r.fulfill({json:{ses_saved:{type:'busy'}}}));
 await page.goto('/chat');await expect(page.getByText('Saved server history')).toBeVisible();await expect(page.getByTitle('停止生成')).toBeVisible();
 await page.reload();await expect(page.getByText('Saved server history')).toBeVisible();expect(submissions).toBe(0);
});

test('permission and question answers use native public endpoints',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('session:agent-code:local-demo','ses_saved'));
 await page.route('**/remote/permission',r=>r.fulfill({json:[{id:'per_test',sessionID:'ses_saved',permission:'bash'}]}));
 await page.route('**/remote/question',r=>r.fulfill({json:[{id:'que_test',sessionID:'ses_saved',questions:[{question:'选择输出格式',options:[{label:'CSV',description:'表格'}]}]}]}));
 let permission:any,question:any;
 await page.route('**/remote/permission/per_test/reply',r=>{permission=r.request().postDataJSON();return r.fulfill({json:true})});
 await page.route('**/remote/question/que_test/reply',r=>{question=r.request().postDataJSON();return r.fulfill({json:true})});
 await page.goto('/chat');await page.getByRole('button',{name:'允许一次',exact:true}).click();expect(permission).toEqual({reply:'once'});
 await page.getByPlaceholder('或输入回答').fill('CSV');await page.getByRole('button',{name:'提交回答',exact:true}).click();expect(question).toEqual({answers:[['CSV']]});
});

test('model references open locally without a connection error or catalog reload',async({page})=>{
 let loads=0;const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/remote/cloud/admin/catalog',r=>{loads++;return r.fulfill({json:{...catalog,models:{'coding-fast':{...model,references:['agent-code']}}}})});
 await page.goto('/admin');
 await expect(page.getByRole('button',{name:'引用关系',exact:true})).toBeVisible();
 const initialLoads=loads;
 await page.getByRole('button',{name:'引用关系',exact:true}).click();
 await expect(page.locator('.json-view')).toContainText('agent-code');
 await expect(page.locator('.notice.error')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'检查连接',exact:true})).toHaveCount(0);
 expect(loads).toBe(initialLoads);expect(errors).toEqual([]);
});

test('reasoning shows one clipped line and expands on demand across history reloads',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('session:agent-code:local-demo','ses_saved'));
 const first='First reasoning line '.repeat(30),second='Second reasoning line stays collapsed';
 await page.route('**/remote/session/ses_saved/message',r=>r.fulfill({json:[{info:{id:'msg_saved',role:'assistant',sessionID:'ses_saved'},parts:[{id:'reason',type:'reasoning',text:first+'\n'+second},{id:'answer',type:'text',text:'Final answer'}]}]}));
 await page.goto('/chat');
 const reasoning=page.locator('.reasoning'),preview=reasoning.locator('.reasoning-preview');
 await expect(preview).toContainText('First reasoning line');
 await expect(reasoning.locator('.reasoning-content')).toBeHidden();
 expect(await preview.evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true);
 await reasoning.locator('summary').click();
 await expect(reasoning.locator('.reasoning-content')).toContainText(second);
 await expect(reasoning.locator('.reasoning-content')).toBeVisible();
 await reasoning.locator('summary').click();
 await expect(reasoning.locator('.reasoning-content')).toBeHidden();
 await page.setViewportSize({width:390,height:844});await page.reload();
 await expect(preview).toBeVisible();
 await expect(reasoning.locator('.reasoning-content')).toBeHidden();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('file drawer refreshes after idle and manually, and ignores another session',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('session:agent-code:local-demo','ses_saved'));
 let entries:any[]=[{name:'test.txt',type:'file',size:0}],loads=0;
 await page.route('**/remote/cloud/files/list?*',r=>{loads++;return r.fulfill({json:{entries}})});
 await page.goto('/chat');await page.getByTitle('查看产物').click();
 await expect(page.locator('.drawer')).toContainText('test.txt');
 entries=[...entries,{name:'report.txt',type:'file',size:42}];
 await page.evaluate(()=>{(window as any).__events.enqueue(new TextEncoder().encode('data: '+JSON.stringify({type:'session.idle',properties:{sessionID:'ses_saved'}})+'\n\n'))});
 await expect(page.locator('.drawer')).toContainText('report.txt');
 entries=[...entries,{name:'manual.txt',type:'file',size:5}];
 await page.getByRole('button',{name:'刷新文件',exact:true}).click();
 await expect(page.locator('.drawer')).toContainText('manual.txt');
 const previous=loads;
 await page.evaluate(()=>{(window as any).__events.enqueue(new TextEncoder().encode('data: '+JSON.stringify({type:'session.idle',properties:{sessionID:'ses_other'}})+'\n\n'))});
 await page.getByRole('button',{name:'新对话',exact:true}).click();
 await expect(page.locator('.drawer')).toHaveCount(0);expect(loads).toBe(previous);
});

test('configuration viewers distinguish saved configuration and live form JSON',async({page})=>{
 await page.route('**/remote/cloud/admin/config-preview',r=>r.fulfill({json:{scope:'resource-library',models:{sample:{api_key:'must-not-show'}},resources:{},active_gateway:{model_list:[]},gateway_version:1}}));
 await page.goto('/admin');await page.getByRole('button',{name:'全局 JSON',exact:true}).click();
 await expect(page.getByText('全局模型资源库 · 已保存',{exact:true})).toBeVisible();
 await expect(page.locator('.modal')).not.toContainText('must-not-show');
 await page.locator('.modal > .section-heading .icon').click();
 await page.getByRole('button',{name:'MCP',exact:true}).click();await page.getByRole('button',{name:'新建',exact:true}).click();
 await page.getByLabel('名称（字母、数字、横线）').fill('example-mcp');
 await page.getByLabel('服务 URL').fill('https://mcp.example/tools');
 const json=page.locator('.form-config-preview .json-view');
 await expect(json).toContainText('example-mcp');await expect(json).toContainText('https://mcp.example/tools');
 await page.getByLabel('服务 URL').fill('https://mcp.example/changed');
 await expect(json).toContainText('/changed');
});

test('Agent form JSON comes from the server compiler and updates without saving',async({page})=>{
 let saves=0;
 page.on('request',r=>{if(r.method()==='PUT')saves++});
 await page.route('**/remote/cloud/admin/agents/agent-code/config-preview',r=>{const cfg=r.request().postDataJSON().config;return r.fulfill({json:{opencode:{model:'cloud-model-gateway/'+cfg.default_model_id,small_model:cfg.small_model_id},sources:[]}})});
 await page.goto('/admin');await page.getByRole('button',{name:'Agents',exact:true}).click();await page.getByRole('button',{name:'配置 Agent',exact:true}).click();
 await expect(page.locator('.form-config-preview .json-view')).toContainText('cloud-model-gateway/coding-fast');
 await page.getByLabel('小模型（可选）',{exact:true}).selectOption('coding-fast');
 await expect(page.locator('.form-config-preview .json-view')).toContainText('"small_model": "coding-fast"');
 expect(saves).toBe(0);
});
