import { Play } from "lucide-react";


export function AppHeader() {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand__mark" aria-hidden="true"><Play /></span>
        <h1>短视频媒体检查台</h1>
        <span className="brand__note">本地 F2 · 抖音 / TikTok</span>
      </div>
      <div className="service-status"><span />服务就绪</div>
    </header>
  );
}
