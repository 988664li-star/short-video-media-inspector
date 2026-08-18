import { Check, Copy, FileText, LoaderCircle } from "lucide-react";
import { useState } from "react";

import { copyText } from "../../lib/clipboard";
import type { TranscriptionData } from "../../types/douyin";


interface TranscriptPanelProps {
  transcription: TranscriptionData | null;
  loading: boolean;
  error: string;
  onExtract: () => void;
}

const formatTimestamp = (seconds: number) => {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
};

export function TranscriptPanel({ transcription, loading, error, onExtract }: TranscriptPanelProps) {
  const [copied, setCopied] = useState(false);

  const copyTranscript = async () => {
    if (!transcription?.text) return;
    await copyText(transcription.text);
    setCopied(true);
  };

  return (
    <section className="panel transcript-panel" aria-labelledby="transcript-title" aria-busy={loading}>
      <header className="transcript-header">
        <div>
          <span className="transcript-eyebrow"><FileText /> AI 语音识别</span>
          <h2 id="transcript-title">视频文案</h2>
        </div>
        {transcription?.text ? (
          <button className="button button--secondary transcript-copy" type="button" onClick={() => void copyTranscript()}>
            {copied ? <Check /> : <Copy />}
            {copied ? "已复制" : "复制文案"}
          </button>
        ) : (
          <button className="button button--primary transcript-extract" type="button" onClick={onExtract} disabled={loading}>
            {loading ? <LoaderCircle className="transcript-spinner" /> : <FileText />}
            {loading ? "正在提取" : error ? "重新提取文案" : "提取文案"}
          </button>
        )}
      </header>

      {loading ? (
        <div className="transcript-status">
          <LoaderCircle className="transcript-spinner" />
          <div>
            <strong>正在从音轨生成文案</strong>
            <p>首次使用会下载 small 转写模型和中文标点模型，后续作品会直接复用。</p>
          </div>
        </div>
      ) : error ? (
        <div className="transcript-status transcript-status--error">
          <FileText />
          <div>
            <strong>暂时没有生成文案</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : transcription ? (
        <>
          <div className="transcript-meta">
            <span>{transcription.model}</span>
            {transcription.punctuation_model ? <span>{transcription.punctuation_model}</span> : null}
            <span>{transcription.device.toUpperCase()} · {transcription.compute_type}</span>
            <span>{formatTimestamp(transcription.duration_seconds)}</span>
            <span>{transcription.source_kind === "audio" ? "独立音轨" : "视频音轨"}</span>
            <span>{transcription.cached ? "临时缓存" : `${transcription.elapsed_seconds.toFixed(1)} 秒完成`}</span>
          </div>
          <p className="transcript-text">{transcription.text || "没有识别到清晰的人声内容。"}</p>
          {transcription.segments.length > 1 ? (
            <details className="transcript-segments">
              <summary>查看分段时间轴 · {transcription.segments.length} 段</summary>
              <ol>
                {transcription.segments.map((segment) => (
                  <li key={`${segment.start}-${segment.end}`}>
                    <time>{formatTimestamp(segment.start)}</time>
                    <span>{segment.text}</span>
                  </li>
                ))}
              </ol>
            </details>
          ) : null}
        </>
      ) : (
        <div className="transcript-status">
          <FileText />
          <div>
            <strong>按需生成视频文案</strong>
            <p>点击“提取文案”后才会加载模型；文案仅作短时缓存并自动清理。</p>
          </div>
        </div>
      )}
    </section>
  );
}
