import {
  WORKSPACE_ROUTE,
  type WorkspacePage,
} from "../../app/workspaceRoutes";
import { CAPABILITIES } from "../../features/capabilities/catalog";

interface WorkspaceNavigationProps {
  activePage: WorkspacePage;
  onNavigate: (page: WorkspacePage) => void;
}

const NAVIGATION_ITEMS = [
  { page: "inspector", label: "作品解析" },
  { page: "capabilities", label: "能力中心", count: CAPABILITIES.length },
  { page: "replication", label: "爆款复刻" },
] as const;

export function WorkspaceNavigation({ activePage, onNavigate }: WorkspaceNavigationProps) {
  return (
    <nav className="workspace-nav" aria-label="工作区">
      {NAVIGATION_ITEMS.map((item) => (
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
          {item.label}
          {"count" in item ? <span>{item.count}</span> : null}
        </a>
      ))}
    </nav>
  );
}
