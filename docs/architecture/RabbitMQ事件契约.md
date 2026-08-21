# RabbitMQ 事件契约

## 1. 规则

- RabbitMQ 负责可靠传递任务和领域事件；MySQL 负责最终业务状态。
- 发布端采用 Transactional Outbox + publisher confirm。
- 消费端只有在业务写入成功后才发送 manual ack。
- 所有消费者以 `event_id` 幂等；消息可能至少投递一次。
- 消费失败有限次重试，之后进入死信队列（DLQ）；不无限重投。

## 2. 统一消息信封

```json
{
  "event_id": "evt_01J...",
  "event_type": "analysis.requested",
  "event_version": 1,
  "occurred_at": "2026-08-21T10:00:00Z",
  "trace_id": "req_01J...",
  "producer": "content-service",
  "payload": {}
}
```

字段不兼容变更必须增加 `event_version` 或新 `event_type`，不得静默改变旧消费者依赖的字段语义。

## 3. Exchange、Queue 与事件

| Exchange | Routing Key | Queue | 发布者 | 消费者 |
| --- | --- | --- | --- |
| `analysis.events` | `analysis.requested` | `analysis.worker` | 内容与项目服务 | AI Worker |
| `analysis.events` | `analysis.completed` | `analysis.notify` | AI Worker | 通知服务 |
| `analysis.events` | `analysis.failed` | `analysis.notify` | AI Worker | 通知服务 |
| `billing.events` | `payment.succeeded` | `billing.notify` | 支付与积分服务 | 通知服务 |
| `billing.events` | `credit.granted` | `billing.audit` | 支付与积分服务 | 审计/运营任务 |
| `billing.events` | `subscription.changed` | `billing.entitlement` | 支付与积分服务 | 用户服务；仅启用订阅时使用 |

每个业务队列配置对应的 `*.dlq`。失败重试可使用延迟队列或 TTL + dead-letter exchange。

## 4. `analysis.requested`

```json
{
  "event_id": "evt_01",
  "event_type": "analysis.requested",
  "event_version": 1,
  "payload": {
    "job_id": "job_01",
    "project_id": "prj_01",
    "user_id": "usr_01",
    "capability_code": "media.transcription",
    "input_asset_id": "ast_01",
    "price_snapshot": {
      "rule_version": "2026-08-v1",
      "credits_reserved": 30
    },
    "options": {}
  }
}
```

Worker 在领取时以条件更新将 Job 从 `PENDING` 改为 `RUNNING`。若条件更新失败，说明任务已被处理或取消，直接 ack 并结束。

## 5. `analysis.completed` 与 `analysis.failed`

```json
{
  "event_type": "analysis.completed",
  "event_version": 1,
  "payload": {
    "job_id": "job_01",
    "user_id": "usr_01",
    "result_id": "res_01",
    "output_asset_ids": ["ast_out_01"],
    "credits_reserved": 30,
    "credits_final": 30
  }
}
```

失败事件需要包含稳定的 `failure_code`，如 `PROVIDER_REJECTED`、`PROVIDER_TIMEOUT`、`INPUT_INVALID`、`INTERNAL_ERROR`。业务服务根据 Job 状态与是否产生可用结果决定是否创建 `CREDIT_REFUND`。

## 6. 支付事件

`payment.succeeded` 只在支付回调完成验签、金额和商户订单号校验，并且订单已原子更新至 `PAID` 后发布。

```json
{
  "event_type": "payment.succeeded",
  "event_version": 1,
  "payload": {
    "order_id": "ord_01",
    "user_id": "usr_01",
    "provider": "wechat_pay",
    "provider_transaction_id": "txn_01",
    "amount": "29.90",
    "currency": "CNY"
  }
}
```

`credit.granted` 在同一笔订单的 `CREDIT_GRANT` 账本写入成功后发布。不要让通知消费者负责发放积分。
