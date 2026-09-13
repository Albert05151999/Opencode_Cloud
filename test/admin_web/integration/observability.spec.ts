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
 await expect(timeline.getByText("80 ms",{exact:true})).toBeVisible();
 await expect(timeline.getByText("瞬时事件 / 未记录耗时",{exact:true})).toBeVisible();
 await timeline.getByRole("button").filter({hasText:"模型网关"}).click();
 await expect(page.getByRole("heading",{name:"模型网关 · 阶段日志"})).toBeVisible();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
 await page.getByLabel("仅异常").check();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
});
test("chat trace deep link opens detail and module log query remains usable",async({page})=>{
 await mock(page);await page.goto(`/admin?tab=logs&trace=${trace}&session=ses_test`);
 await expect(page.getByRole("region",{name:"调用链详情"})).toBeVisible();
 await page.getByRole("tab",{name:"模块日志",exact:true}).click();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
 await page.getByLabel("日志模块").selectOption("model_gateway");
 await page.getByRole("button",{name:"查询",exact:true}).click();
 await expect(page.getByText("UpstreamTimeout",{exact:true})).toBeVisible();
 await page.getByRole("button",{name:"trace 1234567890ab",exact:false}).click();
 await expect(page.getByRole("region",{name:"调用链详情"})).toBeVisible();
});
