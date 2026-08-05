import { LoaderCircle, ScanLine } from "lucide-react";
import type { KeyboardEvent } from "react";

import { Button } from "../../components/ui/Button";
import { CookiePanel } from "../session/CookiePanel";
import type { SessionStatus } from "../../types/douyin";


interface InputPanelProps {
  shareText: string;
  loading: boolean;
  message: string;
  messageTone: "default" | "success" | "error";
  onShareTextChange: (value: string) => void;
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
  loading,
  message,
  messageTone,
  onShareTextChange,
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
        <h2 id="input-heading">粘贴分享内容</h2>
        <Button variant="text" onClick={onReset}>清空</Button>
      </div>
      <div className="input-row">
        <textarea
          className="share-input"
          value={shareText}
          onChange={(event) => onShareTextChange(event.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          aria-label="抖音分享文案或链接"
        />
        <Button
          variant="primary"
          className="resolve-button"
          disabled={loading}
          onClick={onResolve}
          icon={loading ? <LoaderCircle className="spin" /> : <ScanLine />}
        >
          {loading ? "正在解析" : "解析媒体"}
        </Button>
      </div>
      <div className={`main-message main-message--${messageTone}`} role="status">{message}</div>
      <CookiePanel {...session} onSave={session.save} onClear={session.clear} />
    </section>
  );
}
