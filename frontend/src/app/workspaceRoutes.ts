export const WORKSPACE_ROUTE = {
  inspector: "/",
  capabilities: "/capabilities",
  replication: "/replication",
} as const;

export type WorkspacePage = keyof typeof WORKSPACE_ROUTE;

export const WORKSPACE_PAGE_TITLE: Record<WorkspacePage, string> = {
  inspector: "作品解析",
  capabilities: "能力中心",
  replication: "爆款复刻",
};

const PATH_TO_PAGE: Record<string, WorkspacePage> = {
  [WORKSPACE_ROUTE.inspector]: "inspector",
  [WORKSPACE_ROUTE.capabilities]: "capabilities",
  [WORKSPACE_ROUTE.replication]: "replication",
};

export function getWorkspacePage(pathname: string): WorkspacePage {
  return PATH_TO_PAGE[pathname] ?? "inspector";
}
