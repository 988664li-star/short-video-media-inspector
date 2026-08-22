# 轻量 MVP 数据库关系图

本图只覆盖第一版需要落库的核心关系：用户、项目、素材、AI 任务、积分和支付。它不包含 MQ、Outbox、角色权限、订阅和运营配置等可后置的扩展表。

```mermaid
erDiagram
    USERS ||--o{ USER_SESSIONS : has
    USERS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ ASSETS : contains
    PROJECTS ||--o{ ANALYSIS_JOBS : creates
    ASSETS ||--o{ ANALYSIS_JOBS : input_for
    ANALYSIS_JOBS ||--o| JOB_RESULTS : produces
    USERS ||--o{ ORDERS : places
    PRODUCTS ||--o{ ORDERS : purchased_in
    ORDERS ||--o{ PAYMENT_TRANSACTIONS : records
    USERS ||--o{ CREDIT_LEDGER : owns
    ANALYSIS_JOBS ||--o{ CREDIT_LEDGER : settles
    ORDERS ||--o{ CREDIT_LEDGER : grants
    USERS ||--o{ NOTIFICATIONS : receives

    USERS {
        char id PK
        varchar email UK
        varchar password_hash
        varchar status
        datetime created_at
    }
    USER_SESSIONS {
        char id PK
        char user_id FK
        char device_id
        varchar refresh_token_hash
        datetime expires_at
    }
    PROJECTS {
        char id PK
        char owner_id FK
        varchar name
        varchar status
        datetime created_at
    }
    ASSETS {
        char id PK
        char project_id FK
        char owner_id FK
        varchar bucket
        varchar object_key UK
        varchar content_type
        bigint size_bytes
    }
    ANALYSIS_JOBS {
        char id PK
        char project_id FK
        char input_asset_id FK
        char user_id FK
        varchar capability_code
        varchar status
        int credits_reserved
        varchar idempotency_key
    }
    JOB_RESULTS {
        char id PK
        char job_id FK
        char output_asset_id FK
        json result_payload
        datetime completed_at
    }
    PRODUCTS {
        char id PK
        varchar product_type
        varchar name
        decimal price_amount
        int credits_grant
        boolean enabled
    }
    ORDERS {
        char id PK
        char user_id FK
        char product_id FK
        varchar status
        decimal amount
        varchar idempotency_key
        datetime paid_at
    }
    PAYMENT_TRANSACTIONS {
        char id PK
        char order_id FK
        varchar provider
        varchar provider_transaction_id UK
        varchar status
        datetime created_at
    }
    CREDIT_LEDGER {
        char id PK
        char user_id FK
        varchar entry_type
        int amount
        int balance_after
        varchar reference_type
        char reference_id
        datetime occurred_at
    }
    NOTIFICATIONS {
        char id PK
        char user_id FK
        varchar type
        json payload
        datetime read_at
    }
```

## 先实现的表

1. `users`、`user_sessions`：登录与多设备会话。
2. `projects`、`assets`：项目与 MinIO 对象元数据；文件本体不进 MySQL。
3. `analysis_jobs`、`job_results`：任务状态与结果索引；不依赖 MQ。
4. `products`、`orders`、`payment_transactions`、`credit_ledger`：积分购买、支付回调和不可变账本。
5. `notifications`：站内通知，可晚于主流程落地。

## 需要先定下来的约束

- `users.email` 唯一；邮箱统一转小写后再保存。
- `assets.object_key` 唯一；建议包含环境、用户、项目和素材 ID。
- `analysis_jobs` 与 `orders` 都使用 `(user_id, idempotency_key)` 唯一约束，防止重复创建和重复扣费。
- `payment_transactions.provider_transaction_id` 唯一，避免支付回调重复入账。
- `credit_ledger` 只插入、不更新和不删除；余额以账本计算或由快照加速读取。
