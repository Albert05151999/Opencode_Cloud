import {useEffect,useState} from 'react';
import {Dict,remote} from './api';

export function ProviderFields({value,parameters,onTemplate}:{value:Dict,parameters:string,onTemplate:(v:Dict)=>void}){
 const[templates,setTemplates]=useState<Dict[]>([]),[selected,setSelected]=useState(''),[result,setResult]=useState<Dict|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;remote('/cloud/admin/provider-templates').then(v=>{if(active && Array.isArray(v))setTemplates(v)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 const template=templates.find(t=>t.id===selected);
 return <section className="panel"><label>厂商模板<select aria-label="厂商模板" value={selected} onChange={e=>{setSelected(e.target.value);const chosen=templates.find(t=>t.id===e.target.value);if(chosen)onTemplate({provider:chosen.provider,base_url:chosen.base_url})}}><option value="">自定义 / 保持现有配置</option>{templates.map(t=><option value={t.id} key={t.id}>{t.name}</option>)}</select></label>{template&&<p className="muted">{template.notes} {template.example_model&&`示例模型：${template.example_model}（需账户支持）`} <a href={template.docs} target="_blank" rel="noreferrer">厂商说明</a></p>}
 <p className="muted">平台 ID 是 Agent 选择的名称；上游模型 ID 是厂商实际模型名称。保存 → 发布模型网关 → 分配给 Agent → 发布 Agent。</p>
 <button type="button" className="secondary" disabled={busy||value.legacy} onClick={async()=>{setBusy(true);setError('');setResult(null);try{const{references,...model}=value;setResult(await remote('/cloud/admin/models/test-draft','POST',{model:{...model,parameters:JSON.parse(parameters)}}))}catch(e:any){setError(e.message)}finally{setBusy(false)}}}>{busy?'正在隔离环境测试…':'测试当前表单（不保存、不发布）'}</button>{error&&<p role="alert">{error}</p>}{result&&<p role="status">{result.ok?'当前表单测试通过':`测试失败：${result.error}`} · 全局网关未修改</p>}</section>;
}
