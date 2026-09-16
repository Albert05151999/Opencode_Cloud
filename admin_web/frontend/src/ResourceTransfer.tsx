import "./operations-design.css";
import { Upload, Download, FolderOpen } from "lucide-react";
import { AgentTemplates } from "./AgentTemplates";
import { useState } from "react";
import { Dict, remote, download, request } from "./api";

export function ResourceTransfer({ onChanged }: { onChanged: () => void }) {
  const [password, setPassword] = useState(""),
    [credentials, setCredentials] = useState(false);
  const [localPath, setLocalPath] = useState(""),
    [external, setExternal] = useState(false);
  const [preview, setPreview] = useState<Dict | null>(null),
    [choices, setChoices] = useState<Dict>({}),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [result, setResult] = useState("");
  async function inspect(file: File) {
    if (file.size > 20 * 1024 * 1024) { setPreview(null); setError("文件超过 20 MiB，请缩小资源包后重新上传。"); return; }
    setBusy(true);
    setError("");
    setResult("");
    setPreview(null);
    try {
      const form = new FormData();
      form.set("file", file);
      if (password) form.set("password", password);
      const data = await remote("/cloud/admin/imports/preview", "POST", form);
      setPreview(data);
      setChoices(
        Object.fromEntries(
          data.items.map((item: Dict) => [
            item.key,
            { selected: !item.error, target_id: item.id, replace: false },
          ]),
        ),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function inspectLocal() {
    setBusy(true);
    setError("");
    setResult("");
    setPreview(null);
    try {
      const data = await request("/local/imports/preview", "POST", {
        file: localPath,
        include_external_skills: external,
      });
      setPreview(data);
      setChoices(
        Object.fromEntries(
          data.items.map((item: Dict) => [
            item.key,
            { selected: !item.error, target_id: item.id, replace: false },
          ]),
        ),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const selections = Object.entries(choices)
        .filter(([, choice]: any) => choice.selected)
        .map(([key, choice]: any) => ({
          key,
          target_id: choice.target_id,
          replace: choice.replace,
        }));
      const value = await remote(
        `/cloud/admin/imports/${preview.preview_id}/commit`,
        "POST",
        { selections },
      );
      setResult(
        `已导入 ${value.imported.length} 项全局草稿。请分别发布资源，再到 Agent 页面选择版本并发布。`,
      );
      setPreview(null);
      onChanged();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ops-design ops-transfer">
      <section className="panel ops-panel ops-import">
      <div className="section-heading"><h2>资源导入与导出</h2><span className="ops-badge">导入后保存为草稿</span></div>
      <ol className="ops-steps" aria-label="导入流程"><li><b>1</b>选择来源</li><li><b>2</b>核对预览</li><li><b>3</b>导入草稿</li></ol>
      <p className="muted">
        支持原生 OpenCode JSON/JSONC 中的模型和 MCP、单个 SKILL.md、单 Skill
        ZIP，以及本平台资源配置文件。上传上限 20
        MiB。所有导入先保存到全局资源池，不自动分配或发布。
      </p>
      <div className="ops-source-block"><h3><FolderOpen size={18} aria-hidden="true" /> 从本机配置收集</h3>
      <div className="actions">
        <input
          aria-label="本机原生配置路径"
          placeholder="opencode.json / jsonc 完整路径"
          value={localPath}
          onChange={(e) => setLocalPath(e.target.value)}
        />
        <button disabled={busy || !localPath} onClick={inspectLocal}>
          收集模型、MCP 和 Skills 并预览
        </button>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={external}
          onChange={(e) => setExternal(e.target.checked)}
        />
        允许读取配置明确引用的外部 Skill 目录
      </label>
      </div>
      <div className="ops-source-block"><h3><Upload size={18} aria-hidden="true" /> 上传或导出资源包</h3>
      <div className="actions">
        <label className="secondary">
          选择配置或 Skill 附件
          <input
            aria-label="导入资源文件"
            type="file"
            accept=".json,.jsonc,.md,.zip"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void inspect(file);
              e.target.value = "";
            }}
          />
        </label>
        <button
          disabled={busy}
          className="secondary"
          onClick={async () => {
            try {
              await download(
                "/cloud/admin/exports/resources",
                "cloud-resources.json",
              );
            } catch (e: any) {
              setError(e.message);
            }
          }}
        >
          <Download size={16} aria-hidden="true" /> 导出资源配置
        </button>
      </div>
      </div>
      <details className="ops-encrypted">
        <summary>加密资源包</summary>
        <label>
          包口令（至少 12 个字符；导入加密包时也在此填写）
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={credentials}
            onChange={(e) => setCredentials(e.target.checked)}
          />
          在加密包中包含模型和 MCP 凭据
        </label>
        <button
          disabled={busy || password.length < 12}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              const value = await remote(
                "/cloud/admin/exports/encrypted",
                "POST",
                { password, include_credentials: credentials },
              );
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(value)], { type: "application/json" }),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "cloud-resources.encrypted.json";
              a.click();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
              setPassword("");
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          导出加密资源包
        </button>
        <p className="muted">
          包口令不会保存在浏览器持久存储。加密包使用上方相同的选择文件、预览和导入流程；普通文件导入前请清空口令。
        </p>
      </details>
      <p className="notice">
        普通导出的结构化凭据会脱敏，Skill 附件原样保留；不包含会话和工作区。包含
        Agent
        待恢复模板和资源历史版本；旧环境变量模型需在目标端配置，排除项写在导出文件
        warnings 中。原生 skills 路径不是附件，请单独上传实际 Skill 文件。
      </p>
      {error && (
        <p role="alert" className="notice error">
          {error}
        </p>
      )}
      {result && (
        <p role="status" className="notice success">
          {result}
        </p>
      )}
      {busy && <p>正在处理…</p>}
      {preview && (
        <>
          <h3>导入预览</h3><p className="ops-caption">{preview.items.length} 项资源 · 核对目标 ID 与替换选项后提交</p>
          {preview.warnings.map((warning: string, i: number) => (
            <p className="notice" key={i}>
              {warning}
            </p>
          ))}
          {preview.items.map((item: Dict) => (
            <div className="resource-row ops-preview-row" key={item.key}>
              <input
                type="checkbox"
                aria-label={`选择 ${item.id}`}
                disabled={!!item.error}
                checked={choices[item.key]?.selected || false}
                onChange={(e) =>
                  setChoices({
                    ...choices,
                    [item.key]: {
                      ...choices[item.key],
                      selected: e.target.checked,
                    },
                  })
                }
              />
              <div className="grow">
                <strong>
                  {item.name} · {item.kind}
                </strong>
                <p>{item.error || item.warnings?.join("；") || "校验通过"}</p>
                {item.files?.length > 0 && (
                  <details>
                    <summary>附件文件列表</summary>
                    <pre>{item.files.join("\n")}</pre>
                  </details>
                )}
                <details>
                  <summary>配置 JSON</summary>
                  <pre>{JSON.stringify(item.data, null, 2)}</pre>
                </details>
                <label>
                  目标资源 ID
                  <input
                    aria-label={`目标 ID ${item.id}`}
                    value={choices[item.key]?.target_id || ""}
                    onChange={(e) =>
                      setChoices({
                        ...choices,
                        [item.key]: {
                          ...choices[item.key],
                          target_id: e.target.value,
                        },
                      })
                    }
                  />
                </label>
                {item.conflict && (
                  <p className="notice warning">
                    同名资源已存在：请改名，或明确替换草稿；已有发布版本不变。
                  </p>
                )}
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={choices[item.key]?.replace || false}
                    onChange={(e) =>
                      setChoices({
                        ...choices,
                        [item.key]: {
                          ...choices[item.key],
                          replace: e.target.checked,
                        },
                      })
                    }
                  />
                  允许替换同名全局草稿
                </label>
              </div>
            </div>
          ))}
          <button
            className="primary"
            disabled={
              busy || !Object.values(choices).some((c: any) => c.selected)
            }
            onClick={commit}
          >
            导入到全局资源池草稿
          </button>
        </>
      )}
      </section>
      <AgentTemplates onChanged={onChanged} />
    </div>
  );
}
