import { Clapperboard, FileSearch, LayoutGrid, Play } from "lucide-react";

import { WORKSPACE_ROUTE, type WorkspacePage } from "../../app/workspaceRoutes";
import { CAPABILITIES } from "../../features/capabilities/catalog";

interface WorkspaceNavigationProps {
  activePage: WorkspacePage;
  onNavigate: (page: WorkspacePage) => void;
}

const NAVIGATION_ITEMS = [
  { page: "inspector", label: "作品解析", icon: FileSearch },
  { page: "capabilities", label: "能力中心", icon: LayoutGrid, count: CAPABILITIES.length },
  { page: "replication", label: "爆款复刻", icon: Clapperboard },
] as const;

export function WorkspaceNavigation({ activePage, onNavigate }: WorkspaceNavigationProps) {
  return (
    <nav className="workspace-nav" aria-label="工作区">
      <div className="workspace-nav__brand">
        <span className="workspace-nav__brand-mark" aria-hidden="true"><Play /></span>
        <div><strong>短视频媒体检查台</strong><small>本地 F2 工作台</small></div>
      </div>
      <div className="workspace-nav__links">
        {NAVIGATION_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <a
              aria-current={activePage === item.page ? "page" : undefined}
              className={activePage === item.page ? "workspace-nav__active" : ""}
              href={WORKSPACE_ROUTE[item.page]}
              key={item.page}
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
        })}
      </div>
      <div className="workspace-nav__footer"><span />服务就绪<small>抖音 / TikTok</small></div>
    </nav>
  );
}
