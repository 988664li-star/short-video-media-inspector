import { LoaderCircle, RefreshCw, Send } from "lucide-react";

import { publicErrorMessage } from "../../api/client";
import { Button } from "../../components/ui/Button";
import type {
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

function getOutputUrl(task: SeedanceTask) {
  const output = task.response.output;
  if (!output || typeof output !== "object") return "";
  const videoUrl = (output as Record<string, unknown>).video_url;
  return typeof videoUrl === "string" ? videoUrl : "";
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
                  分段 {String(task.segment_id).padStart(2, "0")}
                  {task.segment_start_ms !== null && task.segment_end_ms !== null
                    ? ` · ${formatShotTimestamp(task.segment_start_ms / 1000)}–${formatShotTimestamp(task.segment_end_ms / 1000)}`
                    : ""}
                </em>
              ) : null}
              <span>{new Date(task.created_at * 1000).toLocaleString()}</span>
            </div>
            {outputUrl ? <a href={outputUrl} target="_blank" rel="noreferrer">打开结果视频</a> : null}
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
  confirmed: boolean;
  submittingSegmentId: number | null;
  disabled: boolean;
  onSubmit: (segmentId: number) => void;
}

export function SegmentSubmitList({ segments, tasks, confirmed, submittingSegmentId, disabled, onSubmit }: SegmentSubmitListProps) {
  return (
    <ul className="seedance-segment-submit-list">
      {segments.map((segment) => {
        const latestTask = tasks.find((task) => task.segment_id === segment.segment_id);
        const submitting = submittingSegmentId === segment.segment_id;
        return (
          <li key={segment.segment_id}>
            <div>
              <b>分段 {String(segment.segment_id).padStart(2, "0")}</b>
              <span>{formatShotTimestamp(segment.start_ms / 1000)}–{formatShotTimestamp(segment.end_ms / 1000)}</span>
              <small>{latestTask ? `最近任务：${taskStatusLabel(latestTask.status)}` : "尚未提交"}</small>
            </div>
            <Button variant="primary" disabled={disabled || !confirmed || submitting} onClick={() => onSubmit(segment.segment_id)} icon={submitting ? <LoaderCircle className="spin" /> : <Send />}>
              {submitting ? "正在提交" : `提交分段 ${String(segment.segment_id).padStart(2, "0")}`}
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
