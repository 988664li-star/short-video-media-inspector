import { useCallback, useState } from "react";

import { AppHeader } from "../components/layout/AppHeader";
import { PanelState } from "../components/ui/PanelState";
import { useInspector } from "../hooks/useInspector";
import { useSession } from "../hooks/useSession";
import { useUserDrawer } from "../hooks/useUserDrawer";
import type { AwemeSummary } from "../types/douyin";
import { InputPanel } from "../features/inspector/InputPanel";
import { ResultView } from "../features/inspector/ResultView";
import { UserDrawer } from "../features/user/UserDrawer";
import { CapabilityCenter } from "../features/capabilities/CapabilityCenter";
import { CAPABILITIES } from "../features/capabilities/catalog";


export function App() {
  const [activeView, setActiveView] = useState<"inspector" | "capabilities">("inspector");
  const inspector = useInspector();
  const drawer = useUserDrawer();
  const handleSessionCleared = useCallback(() => {
    drawer.close();
    inspector.clear("登录 Cookie 已清除，请重新解析分享链接。");
  }, [drawer.close, inspector.clear]);
  const session = useSession(handleSessionCleared);
  const inspectAweme = useCallback((item: AwemeSummary) => {
    setActiveView("inspector");
    return inspector.resolve({
      shareText: item.douyin_url,
      awemeId: item.aweme_id,
      scrollToResult: true,
    });
  }, [inspector.resolve]);

  return (
    <>
      <div className="app-shell">
        <AppHeader />
        <nav className="workspace-nav" aria-label="工作区">
          <button type="button" className={activeView === "inspector" ? "workspace-nav__active" : ""} onClick={() => setActiveView("inspector")}>作品解析</button>
          <button type="button" className={activeView === "capabilities" ? "workspace-nav__active" : ""} onClick={() => setActiveView("capabilities")}>能力中心 <span>{CAPABILITIES.length}</span></button>
        </nav>
        <main>
          {activeView === "inspector" ? (
            <>
              <InputPanel
                shareText={inspector.shareText}
                platform={inspector.platform}
                loading={inspector.loading}
                message={inspector.message}
                messageTone={inspector.messageTone}
                onShareTextChange={inspector.setShareText}
                onPlatformChange={inspector.setPlatform}
                onResolve={() => void inspector.resolve()}
                onReset={() => {
                  drawer.close();
                  inspector.resetInput();
                }}
                session={session}
              />
              {inspector.data ? (
                <ResultView
                  data={inspector.data}
                  onOpenUser={(user) => void drawer.open(user)}
                  onInspect={inspectAweme}
                  onExtractTranscription={inspector.extractTranscription}
                  transcription={inspector.transcription}
                />
              ) : (
                <section className="panel empty-state">
                  <PanelState
                    type={inspector.loading ? "loading" : "empty"}
                    title={inspector.loading ? "正在解析媒体" : "等待解析媒体"}
                    description={inspector.loading ? "正在请求抖音公开数据，请稍候。" : "粘贴抖音分享文案或链接，音频、视频和图片会显示在这里。"}
                  />
                </section>
              )}
            </>
          ) : (
            <CapabilityCenter session={session} onInspect={inspectAweme} onOpenUser={(user) => void drawer.open(user)} />
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
