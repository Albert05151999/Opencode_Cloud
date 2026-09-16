import { navigateTo } from "./navigation";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Sparkles,
  MessageSquare,
  Settings2,
  Sun,
  Moon,
  ArrowUpRight,
} from "lucide-react";
import { bootstrap, Dict } from "./api";
import { Chat } from "./Chat";
import { Admin } from "./Admin";
import "./style.css";

function App() {
  const [page, setPage] = useState(
    location.pathname.startsWith("/admin") ? "admin" : "chat",
  );
  const [boot, setBoot] = useState<Dict | null>(null),
    [error, setError] = useState(""),
    [dark, setDark] = useState(localStorage.getItem("theme") === "dark");
  useEffect(() => {
    bootstrap()
      .then(setBoot)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);
  const navigate = (p: string) => {
    navigateTo(`/${p}`);
  };
  useEffect(() => {
    const fn = () =>
      setPage(location.pathname.startsWith("/admin") ? "admin" : "chat");
    window.addEventListener("popstate", fn);
    return () => window.removeEventListener("popstate", fn);
  }, []);
  return (
    <div className="app">
      <nav className="rail">
        <a
          className="logo"
          href="/chat"
          onClick={(e) => {
            e.preventDefault();
            navigate("chat");
          }}
          aria-label="OpenCode Cloud"
        >
          <Sparkles size={23} />
        </a>
        <button
          title="会话"
          aria-label="会话"
          className={page === "chat" ? "selected" : ""}
          onClick={() => navigate("chat")}
        >
          <MessageSquare />
        </button>
        <button
          title="管理"
          aria-label="管理"
          className={page === "admin" ? "selected" : ""}
          onClick={() => navigate("admin")}
        >
          <Settings2 />
        </button>
        <div className="rail-space" />
        <button aria-label="切换主题" onClick={() => setDark(!dark)}>
          {dark ? <Sun /> : <Moon />}
        </button>
        <span className="avatar">Z</span>
      </nav>
      <main>
        {boot ? (
          <>
            <header className="app-header">
              <div>
                <strong>OpenCode</strong>
                <span className="muted"> / Cloud workspace</span>
              </div>
              <button
                className="connection-pill"
                onClick={() => navigateTo("/admin?tab=connection")}
                aria-label="服务器连接设置"
              >
                <span className="status-dot" title="已配置的服务器地址；连接状态请在连接设置中测试" />
                {new URL(boot.url).hostname}
                <ArrowUpRight size={13} />
              </button>
            </header>
            {page === "chat" ? (
              <Chat onConnect={() => navigateTo("/admin?tab=connection")} />
            ) : (
              <Admin boot={boot} onConnection={setBoot} />
            )}
          </>
        ) : (
          <div className="empty">{error || "正在连接本地服务…"}</div>
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
