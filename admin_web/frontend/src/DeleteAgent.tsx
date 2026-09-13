import { useState } from "react";
import { Dict, remote } from "./api";

export function DeleteAgent({
  id,
  onChanged,
}: {
  id: string;
  onChanged: () => void;
}) {
  const [preview, setPreview] = useState<Dict | null>(null),
    [confirmation, setConfirmation] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <button
        className="text-button"
        onClick={async () => {
          setError("");
          try {
            setPreview(
              await remote(
                `/cloud/admin/agents/${encodeURIComponent(id)}/delete-preview`,
              ),
            );
            setConfirmation("");
          } catch (e: any) {
            setError(e.message);
          }
        }}
      >
        永久删除…
      </button>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <div className="modal-backdrop">
          <section className="modal">
            <h2>永久删除 Agent</h2>
            <p>
              将删除 {id} 的配置历史、会话和工作区；全局资源保留。操作不可撤销。
            </p>
            <ul>
              <li>关联沙箱：{preview.sandboxes.length}</li>
              <li>会话：{preview.sessions}</li>
              <li>
                工作区及运行配置文件：{preview.files} 个 / {preview.bytes} 字节
              </li>
              <li>私有资源：{preview.private_resources.join(", ") || "无"}</li>
            </ul>
            <p className="muted">
              发布模板和历史备份保留；共享内容存储等待独立回收，不是磁盘擦除功能。
            </p>
            <label>
              输入完整 Agent ID 确认
              <input
                aria-label="确认删除 Agent ID"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
              />
            </label>
            <div className="actions">
              <button disabled={busy} onClick={() => setPreview(null)}>
                取消
              </button>
              <button
                className="primary"
                disabled={busy || confirmation !== id}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await remote(
                      `/cloud/admin/agents/${encodeURIComponent(id)}/delete`,
                      "POST",
                      {
                        request_id: crypto.randomUUID(),
                        preview_id: preview.preview_id,
                        confirmation,
                      },
                    );
                    setPreview(null);
                    onChanged();
                  } catch (e: any) {
                    setError(e.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                确认永久删除
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
