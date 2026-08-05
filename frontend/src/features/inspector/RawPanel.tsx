import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { copyText } from "../../lib/clipboard";


interface RawPanelProps {
  data: Record<string, unknown>;
}

export function RawPanel({ data }: RawPanelProps) {
  const [copied, setCopied] = useState(false);
  const content = JSON.stringify(data, null, 2);
  const copy = async () => {
    await copyText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div>
      <div className="raw-toolbar">
        <span>抖音作品详情接口原始响应</span>
        <Button variant="text" onClick={copy}>{copied ? "已复制" : "复制 JSON"}</Button>
      </div>
      <pre className="raw-json">{content}</pre>
    </div>
  );
}
