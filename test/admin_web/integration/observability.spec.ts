import { test, expect } from "../../../admin_web/frontend/node_modules/@playwright/test/index.mjs";
const trace="1234567890abcdef1234567890abcdef";
const event={timestamp:"2026-09-14T10:00:00.100Z",module:"model_gateway",action:"http_request",span_id:"2222222222222222",trace_id:trace,duration_ms:80,status_code:502,error_code:"UpstreamTimeout",level:"ERROR",path:"/v1/chat/completions",method:"POST"};
const detail={trace_id:trace,spans:[{span_id:"1111111111111111",module:"api_gateway",name:"http_request",offset_ms:0,duration_ms:100,status_code:502,status:"error",events:[]},{span_id:"2222222222222222",parent_span_id:"1111111111111111",module:"model_gateway",name:"http_request",offset_ms:20,duration_ms:80,status_code:502,status:"error",error_code:"UpstreamTimeout",events:[event]},{span_id:"3333333333333333",module:"agent_runtime",name:"model_dispatch",offset_ms:10,duration_ms:null,status:"unknown",events:[]}],events:[event],summary:{duration_ms:100,modules:["api_gateway","model_gateway","agent_runtime"],module_duration_ms:{api_gateway:100,model_gateway:80}},truncated:true};
async function mock(page:any){
 await page.route("**/remote/**",(r:any)=>{const u=new URL(r.request().url());let data:any={};
 if(u.pathname.endsWith("/catalog"))data={models:{},agents:{},resources:{},jobs:{}};
 else if(u.pathname.endsWith("/modules"))data={items:["api_gateway","model_gateway","agent_runtime"]};
 else if(u.pathname.endsWith("/traces/"+trace))data=detail;
 else if(u.pathname.endsWith("/traces"))data={items:[{trace_id:trace,started_at:event.timestamp,path:"/session/ses_test/prompt_async",method:"POST",duration_ms:100,status_code:502,error:true,modules:detail.summary.modules,span_count:3,session_id:"ses_test"}]};
 else if(u.pathname.endsWith("/logs"))data={items:[event]};
 return r.fulfill({json:data});});
}
test("trace waterfall reveals errors and preserves unknown timing",async({page})=>{
 await mock(page);await page.goto("/admin?tab=logs");
 await page.getByRole("button",{name:"查看调用链",exact:false}).click();
 await expect(page.getByText("部分记录",{exact:true})).toBeVisible();
 const timeline=page.getByRole("region",{name:"调用链详情"});
 await expect(timeline.getByRole('button').filter({hasText:'模型调用 #1'})).toHaveCount(0);
 await timeline.getByRole('button').filter({hasText:'API 网关'}).click();
 await expect(timeline.getByText("80 ms",{exact:true})).toBeVisible();
 await expect(page.getByRole("region",{name:"Agent 整轮执行"})).toContainText("未记录整轮运行时区间");
 await timeline.getByRole("button").filter({hasText:"模型调用 #1"}).click();
 await expect(page.getByRole("heading",{name:"模型网关 · 阶段日志"})).toBeVisible();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
 await page.getByLabel("仅异常").check();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
});

test('session history shows sequential turns with runtime and repeated model calls',async({page})=>{
 await mock(page);
 const phases=[{id:'req',kind:'request',started_at:event.timestamp,duration_ms:2,trace_id:trace},
  {id:'runtime',kind:'runtime',started_at:event.timestamp,duration_ms:null,trace_id:trace},
  {id:'model1',kind:'model',started_at:event.timestamp,duration_ms:1800,trace_id:trace},
  {id:'tool',kind:'tool',tool:'bash',started_at:event.timestamp,duration_ms:20,trace_id:trace},
  {id:'model2',kind:'model',started_at:event.timestamp,duration_ms:900,trace_id:trace}];
 await page.route('**/remote/cloud/traces/sessions/ses_test',r=>r.fulfill({json:{session_id:'ses_test',items:[{id:'turn1',started_at:event.timestamp,observed_duration_ms:2800,runtime_observed:true,model_calls:2,runtime:{duration_ms:2800,started_at:event.timestamp,ended_at:event.timestamp},requests:[phases[0]],phases:phases.slice(2)},{id:'turn2',started_at:event.timestamp,observed_duration_ms:900,runtime_observed:false,model_calls:1,phases:[{...phases[2],id:'model3'}]}]}}));
 await page.goto('/admin?tab=logs&session=ses_test');
 const history=page.getByRole('region',{name:'会话运行时间线',exact:true});
 await expect(history.locator('article')).toHaveCount(2);
 await expect(history.getByText('Agent 整轮执行：2.80 s',{exact:true})).toBeVisible();
 await expect(history.getByText('运行时：发起模型调用',{exact:true})).toHaveCount(0);
 await expect(history.getByText('模型请求全程（含上游）',{exact:true})).toHaveCount(3);
 await expect(history.getByText('1.80 s',{exact:true}).first()).toBeVisible();
 await expect(history.getByText('未记录整轮起止；旧的模型发起事件不代表整轮运行时。')).toBeVisible();
 await history.locator('ol').getByRole('button',{name:'查看调用链',exact:true}).first().click();
 const waterfall=page.getByRole('region',{name:'调用链详情'});
 await expect(waterfall.locator('.obs-span')).toHaveCount(1);
 const parent=waterfall.getByRole('button').filter({hasText:'API 网关'});
 await parent.click();await expect(waterfall.locator('.obs-span')).toHaveCount(2);
 await parent.click();await expect(waterfall.locator('.obs-span')).toHaveCount(1);
 await page.getByRole('button',{name:'返回会话时间线'}).click();
 await expect(history.locator('article')).toHaveCount(2);
});
test("chat trace deep link opens detail and module log query remains usable",async({page})=>{
 await mock(page);await page.goto(`/admin?tab=logs&trace=${trace}&session=ses_test`);
 await expect(page.getByRole("region",{name:"调用链详情"})).toBeVisible();
 await page.getByRole("tab",{name:"模块日志",exact:true}).click();
 await expect(page.getByLabel("原始日志预览")).toContainText("UpstreamTimeout");
 await page.getByLabel("日志模块").selectOption("model_gateway");
 await page.getByRole("button",{name:"查询",exact:true}).click();
 await expect(page.getByLabel("原始日志预览")).toContainText("UpstreamTimeout");
 await page.getByRole("tab",{name:"请求调用链",exact:true}).click();
 await page.getByRole("button",{name:"查询",exact:true}).click();
 await expect(page.getByRole("region",{name:"调用链详情"})).toBeVisible();
});

test('serial span endpoints share the same timeline coordinates even for very short spans',async({page})=>{
 await mock(page);
 const serial={...detail,spans:[{span_id:'a',module:'api_gateway',offset_ms:0,duration_ms:.1,events:[]},{span_id:'b',module:'operations',offset_ms:.1,duration_ms:99.9,events:[]}]};
 await page.route('**/remote/cloud/traces/'+trace,r=>r.fulfill({json:serial}));
 await page.goto('/admin?tab=logs&trace='+trace);
 await expect(page.locator('.obs-bar')).toHaveCount(2);
 const bars=await page.locator('.obs-bar').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right}}));
 expect(Math.abs(bars[0].right-bars[1].left)).toBeLessThan(1);
 const columns=await page.locator('.obs-track').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().left));
 expect(columns[0]).toBe(columns[1]);
});

test('session-only filter and raw log download send the selected conditions',async({page})=>{
 await mock(page);await page.goto('/admin?tab=logs');
 const filtered=page.waitForRequest(r=>r.url().includes('/cloud/traces?')&&r.url().includes('session_only=true'));
 await page.getByLabel('仅看有关联会话的调用链').check();await filtered;
 await page.getByRole('tab',{name:'模块日志',exact:true}).click();
 await page.getByLabel('日志模块').selectOption('model_gateway');
 await page.getByLabel('会话 ID',{exact:true}).fill('ses_test');
 await page.getByLabel('追踪 ID').fill(trace);
 await page.route('**/remote/cloud/logs/export?*',r=>r.fulfill({body:JSON.stringify(event)+'\n',contentType:'application/x-ndjson'}));
 const request=page.waitForRequest(r=>r.url().includes('/cloud/logs/export?'));
 const downloaded=page.waitForEvent('download');
 await page.getByRole('button',{name:'下载筛选日志'}).click();
 const url=new URL((await request).url());await downloaded;
 expect(url.searchParams.get('module')).toBe('model_gateway');
 expect(url.searchParams.get('trace_id')).toBe(trace);
 expect(url.searchParams.get('session_id')).toBe('ses_test');
});
