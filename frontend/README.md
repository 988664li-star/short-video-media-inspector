# React 前端

React + TypeScript + Vite 前端只负责界面和交互，通过 `/api` 调用 FastAPI。

```bash
cd frontend
pnpm install
pnpm dev
```

Vite 默认监听所有网卡。局域网使用 `http://<本机局域网IP>:5173` 访问；
开发环境会把 `/api` 代理到本机后端 `http://127.0.0.1:8000`。

目录职责：

- `src/app`：应用组合层，不放具体业务渲染
- `src/features`：按登录态、解析结果、能力中心和用户资料拆分
- `src/components/ui`：跨功能复用的基础控件
- `src/hooks`：异步状态和业务交互
- `src/api`：唯一的 HTTP 访问入口
- `src/types`：前后端数据契约
- `src/styles/tokens.css`：颜色、字号、间距、圆角、阴影的唯一来源
- `src/styles/*.css`：布局、公共控件和各功能样式

能力中心采用请求键缓存和在途请求去重；切换能力或停止输入后自动请求，
同参数切回不重复访问后端。游标分页由结果容器内的滚动观察哨自动触发。

作品解析成功后，`useTranscription` 会自动选择独立音轨；没有独立音轨时回退
到视频音轨。模块级在途请求去重避免重复调用，切换作品时的请求版本校验可
防止旧结果覆盖当前作品。`TranscriptPanel` 展示完整文案、模型信息、复制
操作和可滚动的分段时间轴。

生产构建：

```bash
pnpm build
pnpm preview
```
