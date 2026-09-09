export type Message={info:Record<string,any>,parts:Record<string,any>[]};
export function mergeEvent(messages:Message[],event:Record<string,any>,session:string):Message[]{
  const p=event.properties||{},info=p.info||{},part=p.part||{};
  const sid=p.sessionID||info.sessionID||part.sessionID;
  if(sid!==session)return messages;
  if(event.type==='message.updated'){
    const index=messages.findIndex(m=>m.info.id===info.id);
    if(index<0)return [...messages,{info,parts:[]}];
    return messages.map((m,i)=>i===index?{...m,info:{...m.info,...info}}:m);
  }
  if(event.type==='message.part.updated'){
    const index=messages.findIndex(m=>m.info.id===part.messageID);
    if(index<0)return [...messages,{info:{id:part.messageID,sessionID:session,role:'assistant'},parts:[part]}];
    return messages.map((m,i)=>i!==index?m:{...m,parts:m.parts.some(x=>x.id===part.id)?m.parts.map(x=>x.id===part.id?{...x,...part}:x):[...m.parts,part]});
  }
  if(event.type==='message.part.delta'&&p.field==='text')return messages.map(m=>m.info.id!==p.messageID?m:{...m,parts:m.parts.some(x=>x.id===p.partID)?m.parts.map(x=>x.id===p.partID?{...x,text:(x.text||'')+(p.delta||'')}:x):[...m.parts,{id:p.partID,type:'text',text:p.delta||''}]});
  if(event.type==='message.removed')return messages.filter(m=>m.info.id!==p.messageID);
  return messages;
}
