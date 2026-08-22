import { AudioNode } from "./nodes/AudioNode";
import { CanvasEdge } from "./edges/CanvasEdge";
import { ExtractorNode } from "./nodes/ExtractorNode";
import { ImageNode } from "./nodes/ImageNode";
import { ReplaceableAnalysisNode } from "./nodes/ReplaceableAnalysisNode";
import { ReplacementTaskNode } from "./nodes/ReplacementTaskNode";
import { ShotCollectionNode } from "./nodes/ShotCollectionNode";
import { TextNode } from "./nodes/TextNode";
import { VideoNode } from "./nodes/VideoNode";

export const canvasNodeTypes = {
  text: TextNode,
  image: ImageNode,
  video: VideoNode,
  shot_collection: ShotCollectionNode,
  replaceable_analysis: ReplaceableAnalysisNode,
  replacement_task: ReplacementTaskNode,
  extractor: ExtractorNode,
  music: AudioNode,
  audio: AudioNode,
};

export const canvasEdgeTypes = { canvas: CanvasEdge };
