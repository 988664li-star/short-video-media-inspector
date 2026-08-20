import { LoaderCircle, ScanLine } from "lucide-react";
import type { KeyboardEvent, ReactNode, RefObject } from "react";

import type { ContentPlatform } from "../../api/douyin";
import { Button } from "../../components/ui/Button";
import { VideoStage } from "../inspector/VideoStage";
import type { InspectorData } from "../../types/douyin";

interface ViralRemixCenterProps {
  data: InspectorData | null;
  shareText: string;
  platform: ContentPlatform;
  loading: boolean;
  message: string;
  messageTone: "default" | "success" | "error";
  onShareTextChange: (value: string) => void;
  onPlatformChange: (value: ContentPlatform) => void;
  onResolve: () => void;
  onReset: () => void;
  videoRef?: RefObject<HTMLVideoElement | null>;
  children?: ReactNode;
}

export function ViralRemixCenter({
  data,
  shareText,
  platform,
  loading,
  message,
  messageTone,
  onShareTextChange,
  onPlatformChange,
  onResolve,
  onReset,
  videoRef,
  children,
}: ViralRemixCenterProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") onResolve();
  };

  return (
    <section className="replication-center" aria-labelledby="replication-heading">
      <section className="replication-input-panel panel">
        <div>
          <h2 id="replication-heading">导入参考视频</h2>
          <p>粘贴已获得合法使用权限的参考作品。系统会理解镜头与节奏，再只替换你选中的商品。</p>
        </div>
        <div className="replication-input-actions">
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
        <div className="replication-input-row">
          <textarea
            className="replication-input"
            value={shareText}
            onChange={(event) => onShareTextChange(event.target.value)}
            onKeyDown={handleKeyDown}
            spellCheck={false}
            aria-label="参考作品分享文案或链接"
            placeholder="粘贴抖音或 TikTok 分享文案、作品链接"
          />
          <Button
            variant="primary"
            className="replication-resolve-button"
            disabled={loading}
            onClick={onResolve}
            icon={loading ? <LoaderCircle className="spin" /> : <ScanLine />}
          >
            {loading ? "正在解析" : "解析并提取视频"}
          </Button>
        </div>
        <div className={`replication-message replication-message--${messageTone}`} role="status">{message}</div>
      </section>

      {data ? (
        <div className={`replication-analysis-grid${children ? "" : " replication-analysis-grid--video-only"}`}>
          <section className="replication-result panel" aria-labelledby="replication-video-heading">
            <div className="replication-result__heading">
              <div>
                <h3 id="replication-video-heading">参考视频</h3>
                <p>{data.description || "该作品未提供标题或文案"}</p>
              </div>
              <span>{data.platform === "douyin" ? "抖音" : "TikTok"} · @{data.author.nickname}</span>
            </div>
            <VideoStage data={data} videoRef={videoRef} />
          </section>
          {children}
        </div>
      ) : (
        <section className="replication-empty-state" aria-label="下一步提示">
          <h3>导入后开始配置</h3>
          <p>视频解析完成后，会进入四步流程；每次只需要完成当前一步。</p>
        </section>
      )}
    </section>
  );
}
