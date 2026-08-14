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
- `app/services/session.py`：持久化登录 Cookie，仅向前端返回状态、不返回明文
- `app/services/media.py`：短期媒体注册表和 Range 流代理
- `app/services/transcription.py`：媒体下载、faster-whisper 懒加载、转写与持久缓存
- `app/core`：应用级配置

`/api/capabilities/*` 提供统一的 F2 能力网关，覆盖评论、用户内容、
社交关系、当前账号收藏、Feed、搜索和直播。所有分页接口都统一返回
`pagination.has_more` 与 `pagination.next_cursor`；需要登录的接口会在
Cookie 缺失时返回 `401`，不会向上游发送无意义的游客请求。

登录 Cookie 默认保存在 `backend/data/douyin_cookie.json`。该目录已被 Git
忽略，运行时会设置为仅当前系统用户可读写；也可以通过
`DOUYIN_COOKIE_STORE_PATH` 环境变量修改保存位置。

## 本地文案生成

`POST /api/transcription` 只接受当前媒体注册表中的音频或视频代理地址，
不接受任意外部 URL。模型首次使用时下载，随后保持单例并串行执行推理；
结果按作品 ID、模型和语言缓存在 `backend/data/transcriptions/`。作品没有
独立音轨时，前端会把视频代理交给同一个接口，由 PyAV 直接读取其中的声音。

默认配置适合普通开发机：

```bash
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=8
PUNCTUATION_MODEL=ct-punc
PUNCTUATION_DEVICE=cpu
WHISPER_LANGUAGE=zh
```

这些值都可以在启动 Uvicorn 前通过同名环境变量覆盖。若机器已经正确安装
CUDA 12 和 cuDNN 9，可使用 `WHISPER_DEVICE=cuda` 与
`WHISPER_COMPUTE_TYPE=int8_float16`；加载或推理失败时服务会自动退回 CPU。
