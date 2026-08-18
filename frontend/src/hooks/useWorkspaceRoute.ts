import { useCallback, useEffect, useState } from "react";

import {
  getWorkspacePage,
  WORKSPACE_ROUTE,
  type WorkspacePage,
} from "../app/workspaceRoutes";

function getCurrentPage() {
  return getWorkspacePage(window.location.pathname);
}

export function useWorkspaceRoute() {
  const [page, setPage] = useState(getCurrentPage);

  useEffect(() => {
    const syncPage = () => setPage(getCurrentPage());
    window.addEventListener("popstate", syncPage);
    return () => window.removeEventListener("popstate", syncPage);
  }, []);

  const navigate = useCallback((nextPage: WorkspacePage) => {
    const nextPath = WORKSPACE_ROUTE[nextPage];
    if (window.location.pathname !== nextPath) {
      window.history.pushState(null, "", nextPath);
    }
    setPage(nextPage);
  }, []);

  return { page, navigate };
}
