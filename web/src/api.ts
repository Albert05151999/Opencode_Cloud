export type Dict = Record<string, any>;
let csrf = '';
export async function bootstrap() { const data=await request('/local/bootstrap'); csrf=data.csrf; return data; }
export async function request(path:string, method='GET', body?:unknown, headers:Record<string,string>={}) {
  const form=body instanceof FormData;
  const response=await fetch(path,{method,headers:{...(form?{}:body!==undefined?{'Content-Type':'application/json'}:{}),...(method==='GET'?{}:{'X-Local-CSRF':csrf}),...headers},body:body===undefined?undefined:form?body:JSON.stringify(body)});
  const text=await response.text(); let result:any; try{result=text?JSON.parse(text):{};}catch{result={detail:text.slice(0,300)}}
  if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:`请求失败 (${response.status})`);
  return result;
}
export const remote=(path:string,method='GET',body?:unknown,headers?:Record<string,string>)=>request('/remote'+path,method,body,headers);
export function routeHeaders(agent:string,user:string){return {'X-Cloud-Agent-ID':agent,'X-Cloud-Username':user};}
export async function streamEvents(headers:Record<string,string>, signal:AbortSignal, onEvent:(e:Dict)=>void) {
  const response=await fetch('/remote/event',{headers:{...headers,Accept:'text/event-stream'},signal});
  if(!response.ok||!response.headers.get('content-type')?.startsWith('text/event-stream'))throw Error(`流连接失败 (${response.status})`);
  const reader=response.body!.getReader(),decoder=new TextDecoder(); let buffer='',data:string[]=[];
  try{while(true){const chunk=await reader.read();if(chunk.done)throw Error('事件流已断开');buffer+=decoder.decode(chunk.value,{stream:true});if(buffer.length>2*1024*1024)throw Error('事件帧过大');
    let end;while((end=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,end).replace(/\r$/,'');buffer=buffer.slice(end+1);
      if(line===''){if(data.length){onEvent(JSON.parse(data.join('\n')));data=[];}}else if(line.startsWith('data:'))data.push(line.slice(5).replace(/^ /,''));
    }
  }}finally{reader.releaseLock();await response.body?.cancel().catch(()=>{});}
}
export async function download(path:string,name:string){const response=await fetch('/remote'+path);if(!response.ok)throw Error('下载失败');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
