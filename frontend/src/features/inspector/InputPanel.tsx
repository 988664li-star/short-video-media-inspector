import { LoaderCircle, ScanLine } from "lucide-react";
import type { KeyboardEvent } from "react";

import { Button } from "../../components/ui/Button";
import type { ContentPlatform } from "../../api/douyin";
import { CookiePanel } from "../session/CookiePanel";
import type { SessionStatus } from "../../types/douyin";


interface InputPanelProps {
  shareText: string;
  platform: ContentPlatform;
  loading: boolean;
  message: string;
  messageTone: "default" | "success" | "error";
  onShareTextChange: (value: string) => void;
  onPlatformChange: (value: ContentPlatform) => void;
  onResolve: () => void;
  onReset: () => void;
  session: {
    status: SessionStatus;
    busy: boolean;
    message: string;
    tone: "default" | "success" | "error";
    save: (cookie: string) => Promise<boolean>;
    clear: () => Promise<void>;
  };
}

export function InputPanel({
  shareText,
  platform,
  loading,
  message,
  messageTone,
  onShareTextChange,
  onPlatformChange,
  onResolve,
  onReset,
  session,
}: InputPanelProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") onResolve();
  };

  return (
    <section className="input-panel" aria-labelledby="input-heading">
      <div className="section-heading">
        <h2 id="input-heading">分享链接</h2>
        <div className="input-actions">
          <label className="platform-select-label">
            <span>平台</span>
            <select value={platform} onChange={(event) => onPlatformChange(event.target.value as ContentPlatform)} aria-label="解析平台">
              <option value="auto">自动识别</option>
              <option value="douyin">抖音</option>
              <option value="tiktok">TikTok</option>
            </select>
          </label>
          <Button variant="text" onClick={onReset}>清空</Button>
        </div>
      </div>
      <div className="input-row">
        <textarea
          className="share-input"
          value={shareText}
          onChange={(event) => onShareTextChange(event.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          aria-label="抖音或 TikTok 分享文案或链接"
          placeholder="粘贴抖音分享文案或链接"
        />
        <Button
          variant="primary"
          className="resolve-button"
          disabled={loading}
          onClick={onResolve}
          icon={loading ? <LoaderCircle className="spin" /> : <ScanLine />}
        >
          {loading ? "正在解析" : "解析作品"}
        </Button>
      </div>
      <div className={`main-message main-message--${messageTone}`} role="status">{message}</div>
      <CookiePanel {...session} onSave={session.save} onClear={session.clear} />
    </section>
  );
}
