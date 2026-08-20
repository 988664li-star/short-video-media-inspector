import { useCallback, useEffect, useMemo, useState } from "react";

import { CookiePanel } from "../session/CookiePanel";
import type { AwemeSummary, SessionStatus, UserSummary } from "../../types/douyin";
import { CAPABILITIES, type CapabilityDefinition, type CapabilityField } from "./catalog";
import { CapabilityForm } from "./CapabilityForm";
import { CapabilityResults } from "./CapabilityResults";
import { CapabilitySidebar } from "./CapabilitySidebar";
import { useCapabilityRunner, type CapabilityValues } from "./useCapabilityRunner";


interface CapabilityCenterProps {
  session: {
    status: SessionStatus;
    revision: number;
    busy: boolean;
    message: string;
    tone: "default" | "success" | "error";
    save: (cookie: string) => Promise<boolean>;
    clear: () => Promise<void>;
  };
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  onOpenUser: (user: UserSummary) => void;
}

const INITIAL_VALUES: CapabilityValues = {
  awemeId: "7657015637683801370",
  commentId: "",
  secUserId: "MS4wLjABAAAAmscebfULPJG0kJ_nHdMJi36Y4uviQ0UN4SAX5KbrfAs",
  userId: "111069201508",
  mixId: "",
  folderId: "",
  keyword: "",
  query: "视频剪辑",
  roomId: "",
};

export function CapabilityCenter({ session, onInspect, onOpenUser }: CapabilityCenterProps) {
  const [selectedId, setSelectedId] = useState(CAPABILITIES[0].id);
  const [values, setValues] = useState<CapabilityValues>(INITIAL_VALUES);
  const runner = useCapabilityRunner();
  const definition = useMemo(() => CAPABILITIES.find((item) => item.id === selectedId) || CAPABILITIES[0], [selectedId]);
  const missingInput = definition.fields.some((field) => field !== "userId" && !values[field].trim());
  const loginBlocked = Boolean(definition.loginRequired && !session.status.has_login_markers);
  const requestKey = useMemo(
    () => JSON.stringify([
      definition.id,
      session.revision,
      definition.fields.map((field) => [field, values[field].trim()]),
    ]),
    [definition, session.revision, values],
  );

  useEffect(() => {
    if (missingInput || loginBlocked) {
      runner.clearVisible();
      return;
    }
    const timer = window.setTimeout(() => {
      void runner.run(definition, values, requestKey);
    }, 280);
    return () => window.clearTimeout(timer);
  }, [definition, loginBlocked, missingInput, requestKey, runner.clearVisible, runner.run, values]);

  const select = (next: CapabilityDefinition) => {
    if (next.id === selectedId) return;
    setSelectedId(next.id);
  };
  const change = (field: CapabilityField, value: string) => setValues((current) => ({ ...current, [field]: value }));
  const useFolder = (folderId: string) => {
    setValues((current) => ({ ...current, folderId }));
    setSelectedId("folder-posts");
  };
  const loadMore = useCallback(() => {
    void runner.loadMore(definition, values);
  }, [definition, runner.loadMore, values]);

  return (
    <section className="capability-center">
      <div className="capability-intro panel">
        <div><span className="capability-eyebrow">公开内容与账号数据</span><h2>抖音能力中心</h2><p>把公开能力与登录能力统一成可分页、可预览、可继续解析的操作面板。</p></div>
        <span className="capability-count">{CAPABILITIES.length} 项能力</span>
      </div>
      <CookiePanel {...session} onSave={session.save} onClear={session.clear} />
      <div className="capability-workspace panel">
        <CapabilitySidebar selectedId={selectedId} hasLogin={session.status.has_login_markers} onSelect={select} />
        <div className="capability-main">
          <CapabilityForm definition={definition} values={values} loading={runner.loading} hasLogin={session.status.has_login_markers} onChange={change} />
          <CapabilityResults output={runner.output} loading={runner.loading} loadingMore={runner.loadingMore} error={runner.error} onInspect={onInspect} onOpenUser={onOpenUser} onLoadMore={loadMore} onUseFolder={useFolder} />
        </div>
      </div>
    </section>
  );
}
