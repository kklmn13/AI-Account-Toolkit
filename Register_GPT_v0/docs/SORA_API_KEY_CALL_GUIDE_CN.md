# Sora Key 调用说明

这份文档说明如何调用本项目生成的 `srk_...` Key。

适用范围：

- 文生视频 Key
- 图生视频 Key
- 文生 + 图生 Key
- 账号轮换池 Key

## 1. 先说清楚这把 Key 是什么

- 这不是 OpenAI 官方 API Key。
- 这把 Key 只能调用你本机这个项目暴露出来的本地包装接口。
- 本地后端基址是：

```text
http://127.0.0.1:1989
```

不要用 `8000`。

## 2. 鉴权方式

推荐写法：

```http
Authorization: Bearer srk_xxx
```

也支持：

```http
X-API-Key: srk_xxx
```

下面示例统一用 `Authorization`。

## 3. Key 类型说明

### 3.1 文生视频 Key

作用：

- 可以调用文生视频创建接口
- 可以调用视频任务查询 / 列表 / 取消 / 归档

不能做：

- 图片上传
- 图生视频创建

### 3.2 图生视频 Key

作用：

- 可以调用图片上传接口
- 可以调用图生视频创建接口
- 可以调用视频任务查询 / 列表 / 取消 / 归档

不能做：

- 纯文生视频创建

### 3.3 文生 + 图生 Key

作用：

- 文生视频
- 图生视频
- 图片上传
- 任务查询 / 列表 / 取消 / 归档

## 4. 轮换池 Key 是怎么工作的

如果这把 Key 是“轮换池 Key”，后端会自动：

- 从可用 `Registered+Sora` 账号里选账号
- 优先选当前活跃视频任务更少的账号
- 创建任务前先做短租约占位，降低并发撞号概率
- 记住 `task_id -> account_id`
- 后续 `get / cancel / archive` 自动回到原账号，不会查错号

当前“可用账号”的判断条件是：

- `has_sora = 1`
- `sora_enabled = 1`
- `sora_quota_exhausted = 0`
- `refresh_token` 或 `access_token` 至少有一个

## 5. 当前可调用接口

```text
POST /api/sora-api/me
POST /api/sora-api/request

POST /api/sora-api/video-gen/create
POST /api/sora-api/video-gen/create-and-wait
POST /api/sora-api/video-gen/upload-image
POST /api/sora-api/video-gen/create-with-image
POST /api/sora-api/video-gen/get
POST /api/sora-api/video-gen/list
POST /api/sora-api/video-gen/cancel
POST /api/sora-api/video-gen/archive
```

## 6. 最常用调用方式

下面把 `srk_xxx` 换成你的真实 Key。

### 6.1 检查这把 Key 当前用了哪个账号

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/me \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

返回里常见字段：

- `used_account_id`
- `email`
- `me.username`

### 6.2 文生视频：创建任务

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "A cinematic shot of ocean waves at sunrise.",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide"
  }'
```

说明：

- 后端会自动注入 `sora_create_task` sentinel
- 成功终态统一识别为 `succeeded`

常见返回字段：

- `task_id`
- `used_account_id`
- `used_email`
- `status`
- `normalized_status`

### 6.3 文生视频：创建并轮询到出片

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create-and-wait \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "A cinematic shot of ocean waves at sunrise.",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide",
    "poll_interval_seconds": 5,
    "timeout_seconds": 900
  }'
```

如果成功，关键字段一般有：

- `ok: true`
- `task_id`
- `normalized_status: "succeeded"`
- `video_urls`

### 6.4 图生视频：先上传图片

这一步只适用于：

- 图生视频 Key
- 文生 + 图生 Key

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/upload-image \
  -H 'Authorization: Bearer srk_xxx' \
  -F 'file=@/absolute/path/to/source.jpg' \
  -F 'auto_rotate=true'
```

成功后会拿到：

- `media_id`
- `used_account_id`
- `used_email`

### 6.5 图生视频：拿 `media_id` 创建任务

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Animate this still image with gentle natural motion.",
    "source_image_media_id": "media_xxx",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide"
  }'
```

### 6.6 图生视频：一步上传并创建

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create-with-image \
  -H 'Authorization: Bearer srk_xxx' \
  -F 'prompt=Animate this still image with gentle natural motion.' \
  -F 'file=@/absolute/path/to/source.jpg' \
  -F 'auto_rotate=true' \
  -F 'n_variants=1' \
  -F 'n_frames=300' \
  -F 'resolution=360' \
  -F 'orientation=wide'
```

## 7. 任务查询

### 7.1 查单个任务

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/get \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_xxx"
  }'
```

### 7.2 查任务列表

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/list \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "limit": 10,
    "task_type_filter": "videos"
  }'
```

### 7.3 取消任务

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/cancel \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_xxx"
  }'
```

### 7.4 归档任务

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/archive \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_xxx"
  }'
```

## 8. 返回字段怎么看

视频任务相关接口现在统一会尽量返回这些字段：

- `status`: 上游原始状态
- `normalized_status`: 本地归一化状态
- `is_terminal`: 是否终态
- `is_success`: 是否成功终态
- `video_urls`: 已提取到的视频地址列表

成功终态认：

```text
succeeded
```

不是 `completed`。

## 9. Python 调用示例

```python
import requests

BASE_URL = "http://127.0.0.1:1989"
API_KEY = "srk_xxx"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "prompt": "A cinematic shot of ocean waves at sunrise.",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide",
}

resp = requests.post(
    f"{BASE_URL}/api/sora-api/video-gen/create",
    headers=headers,
    json=payload,
    timeout=120,
)

resp.raise_for_status()
print(resp.json())
```

## 10. 常见错误

### 10.1 `401 Unauthorized` / `Invalid API key`

通常是：

- Key 写错了
- Key 被停用了
- Header 没带对

### 10.2 `403 当前 API Key 类型不能调用...`

通常是 Key 类型不匹配：

- 图生 Key 去调文生创建
- 文生 Key 去调图片上传或图生创建

### 10.3 `404`

通常是：

- 打错端口
- 打到了别的服务
- 路径不是 `/api/sora-api/...`

### 10.4 `429` / `quota_exceeded`

表示当前账号额度不足。

如果是轮换池 Key：

- 后端会优先尝试切到下一个可用账号
- 若所有账号都耗尽，就会报出来

### 10.5 `too_many_concurrent_tasks`

表示当前账号并发繁忙，不一定是额度没了。

## 11. 最短可用命令

如果你只是要最短的调用示例，直接用这个：

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "A cinematic shot of ocean waves at sunrise.",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide"
  }'
```

## 12. 文档位置

本说明文件就在：

```text
docs/SORA_API_KEY_CALL_GUIDE_CN.md
```
