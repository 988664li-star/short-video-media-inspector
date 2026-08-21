import { ImagePlus, Link2, Type, Video } from "lucide-react";

interface CanvasNodeToolbarProps {
  onAddText: () => void;
  onAddExtractor: () => void;
  onAddImage: () => void;
  onAddVideo: () => void;
}

export function CanvasNodeToolbar({ onAddText, onAddExtractor, onAddImage, onAddVideo }: CanvasNodeToolbarProps) {
  return (
    <aside className="creative-canvas__tools" aria-label="添加节点">
      <button type="button" title="添加文本节点" onClick={onAddText}><Type /></button>
      <button type="button" title="添加链接提取节点" onClick={onAddExtractor}><Link2 /></button>
      <button type="button" title="新建图片节点" onClick={onAddImage}><ImagePlus /></button>
      <button type="button" title="新建视频节点" onClick={onAddVideo}><Video /></button>
    </aside>
  );
}
