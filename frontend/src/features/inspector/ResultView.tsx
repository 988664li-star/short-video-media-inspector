import type { AwemeSummary, InspectorData, TranscriptionData, UserSummary } from "../../types/douyin";
import { MediaDetails } from "./MediaDetails";
import { MediaPlayback } from "./MediaPlayback";
import { ResultTabs } from "./ResultTabs";
import { TranscriptPanel } from "./TranscriptPanel";


interface ResultViewProps {
  data: InspectorData;
  onOpenUser: (user: UserSummary) => void;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  transcription: {
    data: TranscriptionData | null;
    loading: boolean;
    error: string;
  };
}

export function ResultView({ data, onOpenUser, onInspect, transcription }: ResultViewProps) {
  return (
    <div id="result">
      <div className="result-layout">
        <MediaPlayback data={data} />
        <MediaDetails data={data} onOpenUser={onOpenUser} />
      </div>
      <TranscriptPanel
        key={`transcript-${data.aweme_id}`}
        transcription={transcription.data}
        loading={transcription.loading}
        error={transcription.error}
      />
      <ResultTabs key={data.aweme_id} data={data} onOpenUser={onOpenUser} onInspect={onInspect} />
    </div>
  );
}
