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
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
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
  }, []);
  if (error) return <p role="alert">无法检测服务器能力：{error}</p>;
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
