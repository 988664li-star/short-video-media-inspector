import { useState } from "react";

import { Button } from "../../components/ui/Button";
import type { SessionStatus } from "../../types/douyin";


interface CookiePanelProps {
  status: SessionStatus;
  busy: boolean;
  message: string;
  tone: "default" | "success" | "error";
  onSave: (cookie: string) => Promise<boolean>;
  onClear: () => Promise<void>;
}

export function CookiePanel({
  status,
  busy,
  message,
  tone,
  onSave,
  onClear,
}: CookiePanelProps) {
  const [cookie, setCookie] = useState("");
  const [visible, setVisible] = useState(false);

  const save = async () => {
    if (!cookie.trim()) return;
    if (await onSave(cookie.trim())) setCookie("");
  };

  return (
    <details className="cookie-panel">
      <summary>
        <span className="cookie-panel__summary">
          <strong>登录 Cookie（可选）</strong>
          <small>用于更稳定地访问当前账号有权查看的数据</small>
        </span>
        <span className={`status-chip ${status.configured ? "status-chip--active" : ""}`}>
          {status.configured ? `Cookie 已载入 · ${status.cookie_count} 项` : "游客模式"}
        </span>
      </summary>
      <div className="cookie-panel__content">
        <div className="cookie-guide">
          <strong>需要粘贴什么？</strong>
          <ol>
            <li>在浏览器登录 <code>www.douyin.com</code>，打开开发者工具的 Network。</li>
            <li>刷新页面，选择一个发往 <code>www.douyin.com</code> 的请求。</li>
            <li>在 Request Headers 找到 <code>Cookie</code>，复制冒号后的完整值。</li>
          </ol>
          <p>不要只复制 sessionid，也不要粘贴 Set-Cookie、cURL 或其他请求头。</p>
        </div>
        <label className="field-label" htmlFor="cookieInput">完整 Cookie 值</label>
        <textarea
          id="cookieInput"
          className={`cookie-input ${visible ? "" : "cookie-input--masked"}`}
          value={cookie}
          onChange={(event) => setCookie(event.target.value)}
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder="sessionid=...; sessionid_ss=...; sid_guard=...; uid_tt=...; ttwid=...;"
        />
        <div className="cookie-actions">
          <Button disabled={busy || !cookie.trim()} onClick={save}>载入 Cookie</Button>
          <Button variant="text" aria-pressed={visible} onClick={() => setVisible((value) => !value)}>
            {visible ? "隐藏内容" : "显示内容"}
          </Button>
          {status.configured ? (
            <Button variant="danger" disabled={busy} onClick={onClear}>清除登录态</Button>
          ) : null}
        </div>
        <div className={`inline-message inline-message--${tone}`} role="status">{message}</div>
        <p className="privacy-note">
          Cookie 保存在本机后端私有文件中，后端重启后自动恢复；文件仅允许当前系统用户读写，且不会通过接口回显、写入日志或解析结果。点击“清除登录态”会同时删除内存与持久化文件。
        </p>
        {status.storage_error ? <p className="inline-message inline-message--error">{status.storage_error}</p> : null}
      </div>
    </details>
  );
}
