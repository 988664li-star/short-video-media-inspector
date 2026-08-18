import { CapabilityCenter } from "../features/capabilities/CapabilityCenter";
import type { SessionController } from "../hooks/useSession";
import type { AwemeSummary, UserSummary } from "../types/douyin";

interface CapabilitiesPageProps {
  session: SessionController;
  onInspect: (item: AwemeSummary) => Promise<boolean>;
  onOpenUser: (user: UserSummary) => void;
}

export function CapabilitiesPage({ session, onInspect, onOpenUser }: CapabilitiesPageProps) {
  return <CapabilityCenter session={session} onInspect={onInspect} onOpenUser={onOpenUser} />;
}
