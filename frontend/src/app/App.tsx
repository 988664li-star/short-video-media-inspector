import { lazy, Suspense, useCallback, useState } from "react";

import { AppHeader } from "../components/layout/AppHeader";
import { WorkspaceNavigation } from "../components/layout/WorkspaceNavigation";
import { useInspector } from "../hooks/useInspector";
import { useSession } from "../hooks/useSession";
import { useUserDrawer } from "../hooks/useUserDrawer";
import { useWorkspaceRoute } from "../hooks/useWorkspaceRoute";
import type { AwemeSummary } from "../types/douyin";
import { UserDrawer } from "../features/user/UserDrawer";
import { CapabilitiesPage } from "../pages/CapabilitiesPage";
import { InspectorPage } from "../pages/InspectorPage";
import { ReplicationPage } from "../pages/ReplicationPage";
import { WORKSPACE_PAGE_TITLE } from "./workspaceRoutes";

const CreativeCanvasPage = lazy(async () => {
  const module = await import("../pages/CreativeCanvasPage");
  return { default: module.CreativeCanvasPage };
});

export function App() {
  const { page, navigate } = useWorkspaceRoute();
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const inspector = useInspector();
  const drawer = useUserDrawer();
  const handleSessionCleared = useCallback(() => {
    drawer.close();
    inspector.clear("登录 Cookie 已清除，请重新解析分享链接。");
  }, [drawer.close, inspector.clear]);
  const session = useSession(handleSessionCleared);
  const inspectAweme = useCallback((item: AwemeSummary) => {
    navigate("inspector");
    return inspector.resolve({
      shareText: item.douyin_url,
      awemeId: item.aweme_id,
      scrollToResult: true,
    });
  }, [inspector.resolve, navigate]);
  const resetInspector = useCallback(() => {
    drawer.close();
    inspector.resetInput();
  }, [drawer.close, inspector.resetInput]);

  return (
    <>
      <div className={`app-shell${navigationCollapsed ? " app-shell--nav-collapsed" : ""}`}>
        <WorkspaceNavigation
          activePage={page}
          onNavigate={navigate}
          collapsed={navigationCollapsed}
          onToggleCollapsed={() => setNavigationCollapsed((collapsed) => !collapsed)}
        />
        <div className="workspace-frame">
          {page === "canvas" ? (
            <Suspense fallback={<main className="workspace-main workspace-main--canvas"><section className="creative-canvas-loading">正在加载画布…</section></main>}>
              <CreativeCanvasPage />
            </Suspense>
          ) : (
            <>
              <AppHeader />
              <main className="workspace-main">
                <div className="page-title"><h1>{WORKSPACE_PAGE_TITLE[page]}</h1></div>
                {page === "inspector" ? (
                  <InspectorPage
                    inspector={inspector}
                    session={session}
                    onInspect={inspectAweme}
                    onOpenUser={(user) => void drawer.open(user)}
                    onReset={resetInspector}
                  />
                ) : page === "capabilities" ? (
                  <CapabilitiesPage session={session} onInspect={inspectAweme} onOpenUser={(user) => void drawer.open(user)} />
                ) : (
                  <ReplicationPage
                    inspector={inspector}
                    onReset={resetInspector}
                  />
                )}
              </main>
            </>
          )}
        </div>
      </div>
      <UserDrawer
        user={drawer.user}
        payload={drawer.payload}
        loading={drawer.loading}
        loadingMore={drawer.loadingMore}
        error={drawer.error}
        loadMoreError={drawer.loadMoreError}
        onClose={drawer.close}
        onInspect={inspectAweme}
        onLoadMore={() => void drawer.loadMore()}
      />
    </>
  );
}
