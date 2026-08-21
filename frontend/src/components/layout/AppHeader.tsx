import type { ReactNode } from "react";

interface AppHeaderProps {
  children?: ReactNode;
}

export function AppHeader({ children }: AppHeaderProps) {
  return (
    <header className={`topbar${children ? " topbar--workspace" : ""}`}>
      {children ? <div className="topbar__workspace">{children}</div> : null}
      <span className="topbar__context">抖音 / TikTok 内容工具</span>
    </header>
  );
}
