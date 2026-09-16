import { ReactNode, useEffect, useState } from "react";
import { remote, Dict } from "./api";

export function Capability({
  name,
  children,
}: {
  name: string;
  children: ReactNode;
}) {
  const [value, setValue] = useState<Dict | null>(null),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    setValue(null);
    remote("/cloud/capabilities")
      .then((v) => {
        if (active) setValue(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [attempt, name]);
  if (error) return <div className="notice error" role="alert"><p>无法检测服务器能力：{error}</p><button className="secondary" onClick={() => setAttempt(v => v + 1)}>重试检测</button></div>;
  if (!value) return <p>正在检测接口能力…</p>;
  if (!value[name])
    return (
      <p className="notice">
        此服务器尚不支持这个管理功能。请部署与本地 Web
        配套的新版服务器包，再刷新页面；原有聊天和配置入口仍可使用。
      </p>
    );
  return <>{children}</>;
}
