import {useEffect,useState} from 'react';
import {Dict,remote} from './api';

export function JobHistory(){
 const[offset,setOffset]=useState(0),[data,setData]=useState<Dict>({items:[],total:0}),[error,setError]=useState('');
 async function refresh(){try{setData(await remote(`/cloud/admin/jobs?offset=${offset}&limit=25`));setError('')}catch(e:any){setError(e.message)}}
 useEffect(()=>{void refresh();const t=setInterval(()=>{if(!document.hidden)void refresh()},5000);return()=>clearInterval(t)},[offset]);
 return <section className="panel"><h3>任务记录</h3><button onClick={refresh}>刷新任务</button>{error&&<p role="alert">{error}</p>}{data.items.map((j:Dict)=><div className="resource-row" key={j.id}><div><strong>{j.kind} · {j.target}</strong><p>{j.id} · {j.status} · {j.checkpoint||''}</p>{j.error&&<p>{j.error}</p>}</div>{['queued','validating','waiting'].includes(j.status)&&j.kind!=='agent.delete'&&<button onClick={async()=>{try{await remote(`/cloud/admin/jobs/${j.id}/cancel`,'POST',{});await refresh()}catch(e:any){setError(e.message)}}}>取消任务</button>}</div>)}<div className="actions"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-25))}>上一页</button><span>{data.total} 条记录</span><button disabled={offset+25>=data.total} onClick={()=>setOffset(offset+25)}>下一页</button></div></section>;
}
