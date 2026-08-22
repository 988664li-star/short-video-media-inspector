请将下面的逐片段视觉观察归并为最多 4 个用户可替换主体。只使用输入中已有的 `observation_id`；可以省略低价值观察，不得新增主体或伪造片段关系。

$observations_json

返回结构：

{
  "groups": [
    {
      "observation_ids": ["shot-1-object-1", "shot-2-object-1"],
      "kind": "product",
      "name": "保温杯（含杯盖与吸管）",
      "description": "主要产品：跨片段展示的完整商品，已合并其颜色、角度和固有组件。"
    }
  ]
}
