import { LoaderCircle, RefreshCw, Send } from "lucide-react";

import { publicErrorMessage } from "../../api/client";
import { Button } from "../../components/ui/Button";
import type {
  SeedanceAnchorImagePreview,
  SeedanceTask,
  StoryboardScriptResult,
} from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

const TASK_STATUS_LABELS: Record<string, string> = {
  pending: "等待处理",
  queued: "排队中",
  running: "生成中",
  processing: "处理中",
  succeeded: "已完成",
  failed: "生成失败",
  cancelled: "已取消",
};

function taskStatusLabel(status: string) {
  return TASK_STATUS_LABELS[status] ?? "状态更新中";
}

function videoUrlFrom(value: unknown) {
  if (!value || typeof value !== "object") return "";
  const videoUrl = (value as Record<string, unknown>).video_url;
  return typeof videoUrl === "string" ? videoUrl : "";
}

function getOutputUrl(task: SeedanceTask) {
  // 方舟任务完成时把成片放在 content.video_url。
  return videoUrlFrom(task.response.content);
}

interface SeedanceTaskListProps {
  tasks: SeedanceTask[];
  refreshingTaskId: string;
  onRefresh: (taskId: string) => void;
}

export function SeedanceTaskList({ tasks, refreshingTaskId, onRefresh }: SeedanceTaskListProps) {
  if (!tasks.length) {
    return <p className="seedance-task-list__empty">尚未提交生成任务。上传文件、保存配置和修改提示词都不会调用视频模型。</p>;
  }
  return (
    <ul className="seedance-task-list">
      {tasks.map((task) => {
        const outputUrl = getOutputUrl(task);
        return (
          <li key={task.local_task_id}>
            <div>
              <b>{taskStatusLabel(task.status)}</b>
              {task.segment_id ? (
                <em>
                  连续片段 {String(task.segment_id).padStart(2, "0")}
                  {task.segment_start_ms !== null && task.segment_end_ms !== null
                    ? ` · ${formatShotTimestamp(task.segment_start_ms / 1000)}–${formatShotTimestamp(task.segment_end_ms / 1000)}`
                    : ""}
                </em>
              ) : null}
              <span>{new Date(task.created_at * 1000).toLocaleString()}</span>
            </div>
            {outputUrl ? (
              <section className="seedance-task-result" aria-label="生成结果">
                <video controls preload="metadata" src={outputUrl}>
                  当前浏览器无法播放该结果视频。
                </video>
                <a href={outputUrl} target="_blank" rel="noreferrer">在新窗口打开结果视频</a>
              </section>
            ) : null}
            {task.error_message ? <p>{publicErrorMessage(task.error_message, "生成失败，请稍后重试。")}</p> : null}
            <Button
              variant="text"
              disabled={refreshingTaskId === task.local_task_id}
              onClick={() => onRefresh(task.local_task_id)}
              icon={refreshingTaskId === task.local_task_id ? <LoaderCircle className="spin" /> : <RefreshCw />}
            >
              刷新状态
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

interface SegmentSubmitListProps {
  segments: StoryboardScriptResult["segments"];
  tasks: SeedanceTask[];
  anchorPreviews: SeedanceAnchorImagePreview[];
  confirmed: boolean;
  submittingSegmentId: number | null;
  disabled: boolean;
  onSubmit: (segmentId: number) => void;
}

export function SegmentSubmitList({ segments, tasks, anchorPreviews, confirmed, submittingSegmentId, disabled, onSubmit }: SegmentSubmitListProps) {
  return (
    <ul className="seedance-segment-submit-list">
      {segments.map((segment) => {
        const latestTask = tasks.find((task) => task.segment_id === segment.segment_id);
        const anchorPreview = anchorPreviews.find((item) => item.segment_id === segment.segment_id);
        const submitting = submittingSegmentId === segment.segment_id;
        return (
          <li key={segment.segment_id}>
            <div>
              <b>连续片段 {String(segment.segment_id).padStart(2, "0")}</b>
              <span>{formatShotTimestamp(segment.start_ms / 1000)}–{formatShotTimestamp(segment.end_ms / 1000)}</span>
              <small>{latestTask ? `最近任务：${taskStatusLabel(latestTask.status)}` : "尚未提交"}</small>
            </div>
            <Button variant="primary" disabled={disabled || !confirmed || submitting} onClick={() => onSubmit(segment.segment_id)} icon={submitting ? <LoaderCircle className="spin" /> : <Send />}>
              {submitting ? "正在提交" : `生成连续片段 ${String(segment.segment_id).padStart(2, "0")}`}
            </Button>
            <details className="seedance-segment-submit-list__prompt">
              <summary>查看本片段的关键帧拼图提示词</summary>
              {anchorPreview?.prompt ? (
                <pre>{anchorPreview.prompt}</pre>
              ) : (
                <p>请先点击上方“加载片段拼图提示词”。此操作只读取提示词，不会调用图片或视频模型。</p>
              )}
            </details>
          </li>
        );
      })}
    </ul>
  );
}
