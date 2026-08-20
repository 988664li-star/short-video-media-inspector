# FastAPI 后端

后端负责 HTTP API、抖音数据解析、媒体代理和本地语音转写，不包含前端静态文件。

```bash
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

接口文档：`http://<本机局域网IP>:8000/api/docs`

目录职责：

- `app/api/routes`：按功能拆分的路由层
- `app/schemas`：请求数据校验
- `app/services/douyin`：F2 调用、标准化和业务编排
- `app/services/session.py`：仅内存保存登录 Cookie，仅向前端返回状态、不返回明文
- `app/services/media.py`：短期媒体注册表和 Range 流代理
- `app/services/transcription.py`：媒体下载、faster-whisper 懒加载、转写与持久缓存
- `app/core`：应用级配置

`/api/capabilities/*` 提供统一的 F2 能力网关，覆盖评论、用户内容、
社交关系、当前账号收藏、Feed、搜索和直播。所有分页接口都统一返回
`pagination.has_more` 与 `pagination.next_cursor`；需要登录的接口会在
Cookie 缺失时返回 `401`，不会向上游发送无意义的游客请求。

登录 Cookie 仅保存在当前服务内存，后端重启或用户点击“清除登录态”后立即删除；
不会写入文件、日志或接口响应。

## 本地文案生成

`POST /api/transcription` 只接受当前媒体注册表中的音频或视频代理地址，
不接受任意外部 URL。模型首次使用时下载，随后保持单例并串行执行推理；
结果只会在 `backend/data/transcriptions/` 做短时缓存，默认 30 分钟自动过期；
服务启动和停止时也会清空该目录。作品没有独立音轨时，前端会把视频代理交给
同一个接口，由 PyAV 直接读取其中的声音。

默认配置适合普通开发机：

```bash
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=8
PUNCTUATION_MODEL=ct-punc
PUNCTUATION_DEVICE=cpu
WHISPER_LANGUAGE=zh
TRANSCRIPTION_CACHE_TTL_SECONDS=1800
VOCAL_SEPARATION_ENABLED=true
VOCAL_SEPARATION_MODEL=htdemucs
VOCAL_SEPARATION_DEVICE=cpu
VOCAL_SEPARATION_TIMEOUT_SECONDS=600
MEDIA_SESSION_TTL_SECONDS=600
PRIVACY_CLEANUP_INTERVAL_SECONDS=60
```

这些值都可以在启动 Uvicorn 前通过同名环境变量覆盖。若机器已经正确安装
CUDA 12 和 cuDNN 9，可使用 `WHISPER_DEVICE=cuda` 与
`WHISPER_COMPUTE_TYPE=int8_float16`；加载或推理失败时服务会自动退回 CPU。

## 自动分镜

`POST /api/shot-detection` 仅接受当前媒体注册表中的视频代理地址。服务会下载
源视频并将全部分析资产集中写入 `backend/data/shot_detection/<分析键>/`：

```text
source.mp4
scenes.json
scene_001/
  video.mp4
  candidates/
  selected/
```

每个镜头都会导出独立视频、三张候选帧，并按画面变化自动保留 1–3 张高清关键帧。
网页只通过受限的 `/api/shot-detection/<分析键>/assets/...` 接口读取 `scene_*`
内的素材，不能读取源视频或目录外文件。相同视频和参数会直接读取已有
`scenes.json`，不会重复下载或导出。

默认数据保留 7 天，由后台清理任务回收。可通过以下环境变量调整：

```bash
SHOT_DETECTION_DATA_PATH=backend/data/shot_detection
SHOT_DETECTION_MAX_MEDIA_BYTES=209715200
SHOT_DETECTION_SCENE_THRESHOLD=27
SHOT_DETECTION_MIN_SHOT_SECONDS=0.5
SHOT_DETECTION_CACHE_TTL_SECONDS=604800
SHOT_DETECTION_FFMPEG_BINARY=ffmpeg
```

镜头边界由 PySceneDetect 的 `ContentDetector` 在 CPU 上识别，默认阈值为 27；数值越小
越敏感，越容易切出更多镜头。FFmpeg 负责导出镜头视频和关键帧资产，无需 CUDA。

在自动分镜完成后，前端可按需生成分段分镜脚本：服务会使用已下载的 `source.mp4`
生成 `transcript.json` 和 `scene_packages.json`，将关键帧拼接为分镜图后，再由视觉模型
按片段生成脚本。替换方案随后汇总为 `replica_playbook.json`，用于识别可替换的人物、产品、背景和屏幕元素，并生成视频编辑提示词。这些文件和分镜素材始终
保存在同一个 `backend/data/shot_detection/<分析键>/` 目录。

分段分镜脚本和替换方案需要由服务端环境变量提供密钥，且只有用户点击相应按钮时才会调用：

```bash
SILICONFLOW_API_KEY=你的密钥
# 分段分镜脚本（多图/视频理解）
SILICONFLOW_VISION_MODEL=Qwen/Qwen3-Omni-30B-A3B-Instruct
# 替换方案等纯文本汇总；不填时沿用 SILICONFLOW_MODEL
SILICONFLOW_TEXT_MODEL=Qwen/Qwen3.6-27B
REPLICA_PRIMARY_OVERLAP_SECONDS=0.3
```

## Seedance 2.0 Mini 测试工作台

“替换方案”页会将用户选择的替换对象、方舟 File ID、可编辑提示词和每次任务快照
保存在 `backend/data/replica_workspaces.sqlite3`。用户在网页选择本地图片或视频后，
后端会直接以 multipart 上传到方舟 Files API；页面也会读取该账号下已有的
`user_data` 文件供选择。SQLite 只保存 `file_id`，因此刷新网页、切换分镜标签或重启
服务后仍可恢复素材和提示词的对应关系。

默认只有 Seedance 2.0 Mini：

```bash
# 可选；未配置时“提交 Seedance 测试”会被安全阻断，不会产生调用费用。
ARK_API_KEY=你的方舟 API Key
# 可选覆盖项
REPLICA_WORKSPACE_DB_PATH=backend/data/replica_workspaces.sqlite3
```

上传/选择文件不会调用视频生成模型。保存工作台和修改提示词只写 SQLite。只有用户
勾选计费确认并点击“提交 Seedance 测试”时，后端才会先刷新已选 File ID，拿到有效
下载地址后按官方内容生成协议发送：原视频使用 `reference_video`，已勾选对象的参考图
按工作台顺序使用 `reference_image`，并默认关闭生成音频和水印。每次任务保存独立
请求快照，方便用不同提示词人工对比结果。
