import { LoaderCircle, Video } from "lucide-react";


interface PanelStateProps {
  type?: "empty" | "loading";
  title: string;
  description?: string;
}

export function PanelState({ type = "empty", title, description }: PanelStateProps) {
  const Icon = type === "loading" ? LoaderCircle : Video;
  return (
    <div className={`panel-state panel-state--${type}`}>
      <Icon aria-hidden="true" />
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
