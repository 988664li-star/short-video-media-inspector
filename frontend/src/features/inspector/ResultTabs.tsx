import { useState } from "react";

import type { AwemeSummary, InspectorData, UserSummary } from "../../types/douyin";
import { AuthorPanel } from "./author/AuthorPanel";
import { MediaList } from "./aweme/MediaList";
import { CommentsPanel } from "./comments/CommentsPanel";
import { DetailPanel } from "./details/DetailPanel";
import { RawPanel } from "./RawPanel";


type TabId = "details" | "comments" | "related" | "author" | "raw";

interface ResultTabsProps {
  data: InspectorData;
  onOpenUser: (user: UserSummary) => void;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
}

export function ResultTabs({ data, onOpenUser, onInspect }: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>("details");
  const comments = data.comments?.items || [];
  const related = data.related || [];
  const authorPosts = data.author_posts || [];
  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: "details", label: "作品详情" },
    ...(comments.length ? [{ id: "comments" as const, label: "评论", count: data.comments?.total ?? comments.length }] : []),
    ...(related.length ? [{ id: "related" as const, label: "相关推荐", count: related.length }] : []),
    { id: "author", label: "作者作品", count: authorPosts.length },
    { id: "raw", label: "原始数据" },
  ];

  return (
    <section className="panel extended-panel" aria-labelledby="extended-heading">
      <div className="extended-heading">
        <div><h2 id="extended-heading">完整解析结果</h2><p>仅展示接口实际返回的字段，空值自动隐藏。</p></div>
        <button
          type="button"
          className="button button--secondary"
          onClick={() => {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `${data.aweme_id}.json`;
            link.click();
            URL.revokeObjectURL(url);
          }}
        >下载 JSON</button>
      </div>
      <div className="tab-list" role="tablist" aria-label="解析结果分类">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`tab-button ${activeTab === tab.id ? "tab-button--active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}{tab.count !== undefined ? <span>{tab.count}</span> : null}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
        {activeTab === "details" ? <DetailPanel data={data} /> : null}
        {activeTab === "comments" ? <CommentsPanel items={comments} total={data.comments?.total} onOpenUser={onOpenUser} /> : null}
        {activeTab === "related" ? <MediaList items={related} onInspect={onInspect} /> : null}
        {activeTab === "author" ? <AuthorPanel author={data.author} posts={authorPosts} onOpenUser={onOpenUser} onInspect={onInspect} /> : null}
        {activeTab === "raw" ? <RawPanel data={data.raw_detail} /> : null}
      </div>
    </section>
  );
}
