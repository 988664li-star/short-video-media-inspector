import type { SeedanceGenerationReviewSegment } from "../../types/shotDetection";
import { formatShotTimestamp } from "./shotTime";

interface GenerationReviewPackageProps {
  segments: SeedanceGenerationReviewSegment[];
}

export function GenerationReviewPackage({ segments }: GenerationReviewPackageProps) {
  if (!segments.length) {
    return <p className="generation-instructions__empty">点击“准备审查包”后，在这里查看每段实际会上传的视频、图片和最终指令。</p>;
  }
  return (
    <div className="generation-review-package">
      {segments.map((segment) => (
        <article className="generation-review-package__segment" key={segment.segment_id}>
          <header>
            <div>
              <h5>连续片段 {String(segment.segment_id).padStart(2, "0")}</h5>
              <p>原视频位置：{formatShotTimestamp(segment.start_ms / 1000)}–{formatShotTimestamp(segment.end_ms / 1000)} · 本次上传整段 {((segment.end_ms - segment.start_ms) / 1000).toFixed(2)} 秒视频</p>
            </div>
          </header>
          <div className="generation-review-package__media">
            <figure>
              <figcaption><code>@视频1</code> 本次上传的视频片段</figcaption>
              <video controls preload="metadata" src={segment.source_video.download_url} />
            </figure>
            <figure>
              <figcaption><code>@图片1</code> 本片段最终锚点图</figcaption>
              <img src={segment.anchor_image.download_url} alt={`连续片段 ${segment.segment_id} 的最终锚点图`} />
            </figure>
            <figure>
              <figcaption><code>@图片2</code> 原始完整关键帧拼图</figcaption>
              <img src={segment.source_keyframe_image.download_url} alt={`连续片段 ${segment.segment_id} 的原始关键帧拼图`} />
            </figure>
          </div>
          <div className="generation-review-package__materials">
            <b>商品参考图（会以 <code>@图片3</code> 及后续图片随本次视频任务上传，只用于锁定商品外观）</b>
            {segment.product_references.map((product) => (
              <div key={product.candidate_id}>
                <span>{product.target_description || "目标产品"}</span>
                <ul>
                  {product.assets.map((asset) => <li key={asset.id}><img src={asset.download_url} alt={asset.filename || "目标产品参考图"} /></li>)}
                </ul>
              </div>
            ))}
          </div>
          <details className="generation-instructions__preview">
            <summary>查看最终发送给视频模型的指令</summary>
            <pre>{segment.prompt}</pre>
          </details>
        </article>
      ))}
    </div>
  );
}
