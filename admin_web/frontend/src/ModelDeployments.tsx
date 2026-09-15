import { useEffect, useState } from 'react';
import { Dict, request, remote } from './api';

export function ModelDeployments({ value, parameters, onChange }: { value: Dict; parameters: string; onChange: (v: Dict) => void }) {
  const [testing, setTesting] = useState(''), [results, setResults] = useState<Record<string, string>>({});
  useEffect(() => setResults({}), [value, parameters]);
  const rows: Dict[] = value.deployments || [];
  const update = (id: string, field: string, item: unknown) => onChange({
    ...value, deployments: rows.map(row => row.id === id ? { ...row, [field]: item } : row),
  });
  const add = () => {
    const existing = rows.length ? rows : [
      { id: 'primary', api_key: value.api_key || '', base_url: value.base_url || '', enabled: true },
      ...(value.additional_base_urls || []).map((base: string, i: number) => ({ id: `extra-${i + 1}`, api_key: value.api_key || '', base_url: base, enabled: true })),
    ];
    onChange({ ...value, api_key: '', additional_base_urls: [], deployments: [...existing,
      { id: 'd-' + crypto.randomUUID().slice(0, 12), api_key: '', base_url: '', enabled: true }] });
  };
  return <section className="model-deployments">
    <h3>上游账户与负载均衡</h3>
    <p className="muted">Agent 选择 <code>cloud-model-gateway/{value.id || '平台模型ID'}</code>。
      网关将同一别名映射到下列启用的账户；每次请求选择一个账户，同一个 key 的重复配置不会增加额度。</p>
    <p className="muted">策略：simple-shuffle。可填权重，或按 RPM / TPM 容量分配；均不填时随机选择。容量填写账户实际额度，不是提升额度的开关。</p>
    {rows.map((row, i) => <fieldset className="deployment-card" key={row.id}>
      <legend>账户 {i + 1} · {row.id}</legend>
      <div className="form-grid">
        <label>账户 {i + 1} API key<input type="password" autoComplete="off" value={row.api_key || ''}
          onChange={e => update(row.id, 'api_key', e.target.value)} /></label>
        <label>账户 {i + 1} Base URL<input placeholder={value.base_url || '留空使用模型的默认地址'} value={row.base_url || ''}
          onChange={e => update(row.id, 'base_url', e.target.value)} /></label>
        <label>账户 {i + 1} 上游模型<input placeholder={value.upstream_model || '留空使用默认上游模型'} value={row.upstream_model || ''}
          onChange={e => update(row.id, 'upstream_model', e.target.value)} /></label>
        {(['rpm', 'tpm', 'weight'] as const).map(field => <label key={field}>账户 {i + 1} {field === 'weight' ? '权重' : field.toUpperCase()}
          <input type="number" min={field === 'weight' ? '0.01' : '1'} step={field === 'weight' ? 'any' : '1'} value={row[field] ?? ''}
            onChange={e => update(row.id, field, e.target.value ? Number(e.target.value) : null)} /></label>)}
      </div>
      <div className="actions"><label className="checkbox"><input type="checkbox" checked={row.enabled !== false}
        onChange={e => update(row.id, 'enabled', e.target.checked)} />启用账户 {i + 1}</label>
        <button type="button" className="secondary" disabled={!!testing || row.enabled === false} onClick={async () => {
          setTesting(row.id);
          try {
            const { references, ...model } = value;
            const result = await remote('/cloud/admin/models/test-draft', 'POST', {
              model: { ...model, parameters: JSON.parse(parameters), deployments: [row] },
            });
            setResults(old => ({ ...old, [row.id]: result.ok ? '连接测试通过' : `测试失败：${result.error}` }));
          } catch (e: any) { setResults(old => ({ ...old, [row.id]: e.message })); }
          finally { setTesting(''); }
        }}>{testing === row.id ? '测试中…' : `测试账户 ${i + 1}`}</button>
        <button type="button" className="secondary" disabled={rows.length === 1}
          onClick={() => onChange({ ...value, deployments: rows.filter(item => item.id !== row.id) })}>移除账户 {i + 1}</button></div>
      {results[row.id] && <p role="status">{results[row.id]}</p>}
    </fieldset>)}
    <button type="button" className="secondary" disabled={value.legacy || rows.length >= 32} onClick={add}>
      {rows.length ? '添加上游账户' : '添加独立 API key（启用多账户）'}</button>
  </section>;
}

export function PasteModel({ onApply }: { onApply: (model: Dict) => void }) {
  const [text, setText] = useState(''), [parsed, setParsed] = useState<Dict | null>(null);
  const [selected, setSelected] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  return <details className="model-paste"><summary>粘贴 OpenCode 原生 JSON / JSONC 填入表单</summary>
    <p className="muted">支持完整 opencode.json，也支持已转义的 JSON 字符串；无需手动转义。只解析模型，不导入 MCP、插件或其他配置。</p>
    <label>OpenCode JSON<textarea className="code-editor" value={text} onChange={e => { setText(e.target.value); setParsed(null); }}
      placeholder={'{"provider":{"minimax":{"npm":"@ai-sdk/openai-compatible","options":{"baseURL":"https://api.minimaxi.com/v1","apiKey":"填写密钥"},"models":{"MiniMax-M3":{}}}}}'} /></label>
    <button type="button" className="secondary" disabled={busy || !text.trim()} onClick={async () => {
      setBusy(true); setError(''); setParsed(null);
      try { const result = await request('/local/opencode/parse', 'POST', { text }); setParsed(result); setSelected(result.models[0]?.id || ''); }
      catch (e: any) { setError(e.message); } finally { setBusy(false); }
    }}>{busy ? '解析中…' : '解析 JSON'}</button>
    {error && <p role="alert">{error}</p>}
    {parsed && <>
      {parsed.errors.map((item: Dict, i: number) => <p key={i} role="alert">{item.provider}：{item.error}</p>)}
      {!!parsed.unresolved?.length && <p className="notice warning">环境变量或文件引用未读取，请在表单中补填：{parsed.unresolved.join('、')}</p>}
      {!!parsed.models.length && <label>选择要填入的模型<select value={selected} onChange={e => setSelected(e.target.value)}>
        {parsed.models.map((m: Dict) => <option key={m.id} value={m.id}>{m.name} · {m.upstream_model}</option>)}</select></label>}
      <button type="button" className="primary" disabled={!selected || !!parsed.errors.length} onClick={() => {
        onApply(parsed.models.find((m: Dict) => m.id === selected)); setText(''); setParsed(null);
      }}>填入当前表单（不保存）</button>
    </>}
  </details>;
}
