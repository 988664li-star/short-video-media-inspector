请归并下面的逐片段视觉观察。只使用输入中已有的 observation_id，不得新增主体或片段关系：

$observations_json

返回结构：

{
  "groups": [
    {
      "observation_ids": ["shot-1-object-1", "shot-2-object-2"],
      "kind": "product",
      "name": "统一后的保守主体名称",
      "description": "基于这些观察归纳的主体作用和实际可见范围"
    }
  ]
}
