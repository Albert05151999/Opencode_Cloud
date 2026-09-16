import assert from "node:assert/strict";
import test from "node:test";
import plugin from "../../../catalog_service/resources/agents/agent-code/plugins/trace.mjs";

test("managed message propagates its operation trace without shared state", async () => {
  const hook = (await plugin())["chat.headers"];
  const outputs = [{ headers: {} }, { headers: {} }];
  const traces = ["a".repeat(32), "b".repeat(32)];
  await Promise.all(traces.map((trace, index) => hook(
    { sessionID: `ses_${index}`, message: { id: `msg_${trace}` }, model: { id: "model" } },
    outputs[index],
  )));
  outputs.forEach((output, index) => {
    assert.match(output.headers.traceparent, new RegExp(`^00-${traces[index]}-[0-9a-f]{16}-01$`));
    assert.equal(output.headers["x-cloud-session-id"], `ses_${index}`);
    assert.equal(output.headers["x-cloud-message-id"], `msg_${traces[index]}`);
  });
});

test("unmanaged message is correlated but is not attached to a made-up trace", async () => {
  const hook = (await plugin())["chat.headers"];
  const output = { headers: {} };
  await hook({ sessionID: "ses_custom", message: { id: "custom-message" } }, output);
  assert.equal(output.headers["x-cloud-session-id"], "ses_custom");
  assert.equal(output.headers["x-cloud-message-id"], "custom-message");
  assert.equal(output.headers.traceparent, undefined);
});

test("tool events correlate reversed arrival and concurrent messages without sensitive text", async () => {
 const hook=await plugin(), rows=[], original=console.log;
 console.log=value=>rows.push(JSON.parse(value.split('@@OPENCODE_CLOUD_EVENT@@')[1]));
 const info=(sid,id,trace)=>({event:{type:'message.updated',properties:{info:{role:'assistant',sessionID:sid,id,parentID:'msg_'+trace}}}});
 const tool=(sid,id,status='completed')=>({event:{type:'message.part.updated',properties:{part:{sessionID:sid,messageID:id,id:'prt_a',callID:'call_same',tool:'bash',type:'tool',state:{status,time:{start:100,end:125},input:{key:'SECRET'},output:'PRIVATE',error:'TOKEN'}}}}});
 try {
  hook.event(tool('ses_a','msg_a'));hook.event(info('ses_a','msg_a','a'.repeat(32)));
  hook.event(info('ses_a','msg_b','b'.repeat(32)));hook.event(info('ses_b','msg_a','c'.repeat(32)));
  hook.event(tool('ses_a','msg_b','error'));hook.event(tool('ses_b','msg_a'));hook.event(tool('ses_a','msg_a'));
  assert.equal(rows.length,3);assert.deepEqual(rows.map(x=>x.trace_id),['a','b','c'].map(x=>x.repeat(32)));
  assert.ok(rows.every(x=>x.duration_ms===25 && !('parent_span_id' in x)));
  assert.equal(rows[1].error_code,'ToolExecutionError');assert.doesNotMatch(JSON.stringify(rows),/SECRET|PRIVATE|TOKEN/);
  await hook.dispose();hook.event(tool('ses_a','msg_a'));assert.equal(rows.length,3);
 } finally {console.log=original;}
});

test("unknown timing and evicted associations never fabricate spans", async () => {
 const hook=await plugin(), rows=[], original=console.log;console.log=value=>rows.push(value);
 const info=i=>({event:{type:'message.updated',properties:{info:{role:'assistant',sessionID:'ses_a',id:'msg_'+i,parentID:'msg_'+'a'.repeat(32)}}}});
 const part=i=>({event:{type:'message.part.updated',properties:{part:{sessionID:'ses_a',messageID:'msg_'+i,id:'prt_'+i,callID:'call_'+i,tool:'bash',type:'tool',state:{status:'completed',time:{start:1,end:2}}}}}});
 try {
  for(let i=0;i<1030;i++)hook.event(part(i));
  hook.event(info(0));assert.equal(rows.length,0);
  hook.event(info(1029));assert.equal(rows.length,1);
  for(let i=0;i<1030;i++)hook.event(info(i));
  const count=rows.length;hook.event(part(0));assert.equal(rows.length,count);
  const invalid=part(1028);invalid.event.properties.part.state.time={};hook.event(invalid);assert.equal(rows.length,count);
 } finally {console.log=original;await hook.dispose();}
});

test('runtime spans cover the whole turn, skip tool rounds, and parent model calls', async()=>{
 const hook=await plugin(),rows=[],original=console.log,trace='d'.repeat(32),user='msg_'+trace;
 console.log=v=>rows.push(JSON.parse(v.split('@@OPENCODE_CLOUD_EVENT@@')[1]));
 const message=info=>hook.event({event:{type:'message.updated',properties:{info}}});
 try{
  message({role:'user',sessionID:'ses_a',id:user,time:{created:1000}});
  const headers={headers:{}};await hook['chat.headers']({sessionID:'ses_a',message:{id:user,time:{created:1000}}},headers);
  message({role:'assistant',sessionID:'ses_a',id:'assistant1',parentID:user,time:{completed:2000},finish:'tool-calls'});
  assert.equal(rows.filter(r=>r.action==='runtime_complete').length,0);
  message({role:'assistant',sessionID:'ses_a',id:'assistant2',parentID:user,time:{completed:5000},finish:'stop'});
  message({role:'assistant',sessionID:'ses_a',id:'assistant2',parentID:user,time:{completed:5000},finish:'stop'});
  const spans=rows.filter(r=>r.action==='runtime_complete');assert.equal(spans.length,1);
  assert.equal(spans[0].duration_ms,4000);assert.equal(spans[0].message_id,user);
  assert.equal(headers.headers.traceparent,`00-${trace}-${spans[0].span_id}-01`);
  assert.equal(rows[0].parent_span_id,spans[0].span_id);
  message({role:'assistant',sessionID:'ses_other',id:'assistant3',parentID:user,time:{completed:7000},finish:'stop'});
  assert.equal(rows.filter(r=>r.action==='runtime_complete').length,1);
 }finally{console.log=original;await hook.dispose();}
});
