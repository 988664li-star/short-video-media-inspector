import { useCallback } from "react";

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

export function App() {
  const { page, navigate } = useWorkspaceRoute();
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
      <div className="app-shell">
        <AppHeader />
        <WorkspaceNavigation activePage={page} onNavigate={navigate} />
        <main>
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
            <ReplicationPage inspector={inspector} onReset={resetInspector} />
          )}
        </main>
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
