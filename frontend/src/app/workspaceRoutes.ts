export const WORKSPACE_ROUTE = {
  inspector: "/",
  capabilities: "/capabilities",
  replication: "/replication",
} as const;

export type WorkspacePage = keyof typeof WORKSPACE_ROUTE;

const PATH_TO_PAGE: Record<string, WorkspacePage> = {
  [WORKSPACE_ROUTE.inspector]: "inspector",
  [WORKSPACE_ROUTE.capabilities]: "capabilities",
  [WORKSPACE_ROUTE.replication]: "replication",
};

export function getWorkspacePage(pathname: string): WorkspacePage {
  return PATH_TO_PAGE[pathname] ?? "inspector";
}
