import { PanelState } from "../components/ui/PanelState";
import { InputPanel } from "../features/inspector/InputPanel";
import { ResultView } from "../features/inspector/ResultView";
import type { InspectorController } from "../hooks/useInspector";
import type { SessionController } from "../hooks/useSession";
import type { AwemeSummary, UserSummary } from "../types/douyin";

interface InspectorPageProps {
  inspector: InspectorController;
  session: SessionController;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  onOpenUser: (user: UserSummary) => void;
  onReset: () => void;
}

export function InspectorPage({ inspector, session, onInspect, onOpenUser, onReset }: InspectorPageProps) {
  return (
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
        onReset={onReset}
        session={session}
      />
      {inspector.data ? (
        <ResultView
          data={inspector.data}
          onOpenUser={onOpenUser}
          onInspect={onInspect}
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
  );
}
