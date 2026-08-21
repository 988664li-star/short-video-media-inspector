import { Clapperboard, FileSearch, LayoutGrid, PanelLeftClose, PanelLeftOpen, Play, Replace, Workflow } from "lucide-react";

import { WORKSPACE_ROUTE, type WorkspacePage } from "../../app/workspaceRoutes";
import { CAPABILITIES } from "../../features/capabilities/catalog";

interface WorkspaceNavigationProps {
  activePage: WorkspacePage;
  onNavigate: (page: WorkspacePage) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

const NAVIGATION_ITEMS = [
  { page: "inspector", label: "作品解析", icon: FileSearch },
  { page: "capabilities", label: "能力中心", icon: LayoutGrid, count: CAPABILITIES.length },
  { page: "replication", label: "爆款复刻", icon: Clapperboard },
  { page: "canvas", label: "无限画布", icon: Workflow },
] as const;

export function WorkspaceNavigation({
  activePage,
  onNavigate,
  collapsed,
  onToggleCollapsed,
}: WorkspaceNavigationProps) {
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <nav className={`workspace-nav${collapsed ? " workspace-nav--collapsed" : ""}`} aria-label="工作区">
      <div className="workspace-nav__brand">
        <span className="workspace-nav__brand-mark" aria-hidden="true"><Play /></span>
        <div><strong>短视频媒体检查台</strong><small>抖音 / TikTok</small></div>
      </div>
      <button
        className="workspace-nav__collapse"
        type="button"
        aria-label={collapsed ? "展开导航栏" : "收起导航栏"}
        title={collapsed ? "展开导航栏" : "收起导航栏"}
        onClick={onToggleCollapsed}
      >
        <CollapseIcon aria-hidden="true" />
      </button>
      <div className="workspace-nav__links">
        {NAVIGATION_ITEMS.map((item) => {
          const Icon = item.icon;
          const link = (
            <a
              aria-current={activePage === item.page ? "page" : undefined}
              className={activePage === item.page ? "workspace-nav__active" : ""}
              href={WORKSPACE_ROUTE[item.page]}
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                onNavigate(item.page);
              }}
            >
              <Icon aria-hidden="true" />
              <span className="workspace-nav__label">{item.label}</span>
              {"count" in item ? <em>{item.count}</em> : null}
            </a>
          );

          if (item.page !== "replication") return <div className="workspace-nav__item" key={item.page}>{link}</div>;

          return (
            <div className="workspace-nav__item workspace-nav__item--replication" key={item.page}>
              {link}
              {activePage === "replication" ? (
                <div className="workspace-nav__subnav" aria-label="爆款复刻当前模式">
                  <span className="workspace-nav__subnav-item workspace-nav__subnav-item--active" aria-current="page">
                    <Replace aria-hidden="true" />
                    <span>局部替换</span>
                    <small>当前可用</small>
                  </span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="workspace-nav__footer">媒体解析与创作辅助</div>
    </nav>
  );
}
