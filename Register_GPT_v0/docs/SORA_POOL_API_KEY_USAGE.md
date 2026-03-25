# Sora Pool API Key Usage

## Scope

- This key is for this local project only.
- It calls the local wrapper service under `/api/sora-api/*`.
- It is not an OpenAI official API key.

## Base URL

```text
http://127.0.0.1:1989
```

Notes:

- `1989` is the backend port for this project.
- `8000` on this machine is a different service and cannot be used for these routes.

## Authentication

Use the key in the `Authorization` header:

```http
Authorization: Bearer srk_xxx
```

You can also use:

```http
X-API-Key: srk_xxx
```

## Key Scope

- `text_to_video`: can call text-to-video create routes.
- `image_to_video`: can call image upload / image-to-video create routes.
- `all_video`: can call both.
- List / get / cancel / archive routes now allow any video-capable key.

## Pool Mode

- Pool keys are created with `account_id = 0`.
- The backend automatically picks one available `Registered+Sora` account from the pool.
- Video task creation now prefers the account with the fewest active video tasks, then uses cursor order as a tie-breaker.
- The backend inserts a short-lived reservation before creating the upstream task, so concurrent create requests are less likely to collide on the same account.
- Active task occupancy is released after the task reaches a terminal state such as `succeeded`, `failed`, or `cancelled` via the tracked task routes.
- You do not need to pass `account_id`.

## Main Endpoints

### 1. Check current Sora account

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/me \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### 2. Generic Sora backend request

Only `/backend/*` paths are allowed.

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/request \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "GET",
    "path": "/backend/me",
    "payload": {}
  }'
```

### 3. Create video task

This wrapper route now dispatches by task family:

- Text-to-video: official Sora app / NF2 (`POST /backend/nf/create` or `/backend/nf/bulk_create`)
- Image-to-video: legacy storyboard path (`POST /backend/video_gen`)

The backend will automatically inject the required `sora_create_task` sentinel header.

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "A cinematic shot of ocean waves at sunrise.",
    "n_variants": 4,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide"
  }'
```

Response example:

```json
{
  "ok": true,
  "status_code": 200,
  "task_family": "nf2",
  "task_id": "task_01kkxqmadtex1t51mg3z62x0kh",
  "used_account_id": 13,
  "used_email": "example@outlook.com",
  "data": {
    "id": "task_01kkxqmadtex1t51mg3z62x0kh"
  }
}
```

Optional audio-related fields for text-to-video:

- `audio_caption`: describe ambient sound effects
- `audio_transcript`: provide spoken narration or dialogue

Pool-mode note:

- When you create a video task with a pool key, the backend now remembers `task_id -> used_account_id`.
- Later `get/cancel/archive` calls for that `task_id` will automatically reuse the same account.
- You can still pass `account_id` explicitly if you want to pin requests yourself.
- Success terminal state is `succeeded` (not `completed`).

### 3a. Upload an image for image-to-video

This route uploads the image to the upstream Sora account first and returns a reusable `media_id`.

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/upload-image \
  -H 'Authorization: Bearer srk_xxx' \
  -F 'file=@/absolute/path/to/source.jpg' \
  -F 'auto_rotate=true'
```

Response example:

```json
{
  "ok": true,
  "status_code": 200,
  "media_id": "media_01kkxy9ca6eb1vvtmvnsg5zbcq",
  "used_account_id": 7,
  "used_email": "example@outlook.com"
}
```

### 3c. Create image-to-video task from an uploaded `media_id`

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/create \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Animate this still image with gentle natural motion.",
    "source_image_media_id": "media_01kkxy9ca6eb1vvtmvnsg5zbcq",
    "n_variants": 1,
    "n_frames": 300,
    "resolution": 360,
    "orientation": "wide"
  }'
```

### 3d. One-shot image upload + create

This is the easiest route for frontend or scripts that want a single request.

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

### 3b. Create and wait until terminal state

This route creates the task first, then polls `/video-gen/get` until the task reaches a terminal state or timeout.

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

Response example:

```json
{
  "ok": true,
  "timed_out": false,
  "task_id": "task_01kkxqmadtex1t51mg3z62x0kh",
  "status": "succeeded",
  "normalized_status": "succeeded",
  "is_terminal": true,
  "is_success": true,
  "video_urls": [
    "https://..."
  ],
  "used_account_id": 13,
  "used_email": "example@outlook.com",
  "poll_attempts": 7,
  "elapsed_seconds": 31.2
}
```

### 4. Get video task

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/get \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_01kkxqmadtex1t51mg3z62x0kh"
  }'
```

`/video-gen/get`, `/video-gen/cancel`, `/video-gen/archive`, and `/video-gen/create-and-wait` now also return:

- `normalized_status`: normalized task state, with successful terminal state unified to `succeeded`
- `is_terminal`: whether the task is at a terminal state
- `is_success`: whether the terminal state is successful
- `video_urls`: URLs extracted from the task payload when available

### 5. List video tasks

Use `task_type_filter: "videos"` for the normal video list. This value is what the live Sora backend currently expects.

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/list \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "limit": 10,
    "task_type_filter": "videos"
  }'
```

### 6. Cancel video task

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/cancel \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_01kkxqmadtex1t51mg3z62x0kh"
  }'
```

### 7. Archive video task

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/video-gen/archive \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "task_01kkxqmadtex1t51mg3z62x0kh"
  }'
```

POST example:

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/request \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{
    "method": "POST",
    "path": "/backend/some/path",
    "payload": {
      "foo": "bar"
    }
  }'
```

## Response Shape

`/api/sora-api/me` usually returns:

```json
{
  "ok": true,
  "account_id": 13,
  "email": "example@outlook.com",
  "used_account_id": 13,
  "me": {
    "id": "user_xxx",
    "username": "exampleuser"
  }
}
```

## Common Errors

### 404 Not Found

Usually means you hit the wrong service or port.

Check:

- URL must be `http://127.0.0.1:1989`
- Path must be `/api/sora-api/...`

### 401 Invalid API key

Usually means:

- the key is wrong
- the key is disabled
- you passed the wrong header

### 404 / 429 inside Sora payload

These are upstream Sora/backend results from the selected account, not local routing errors.

### 400 invalid_request when creating video

Usually means the payload shape is wrong.

Use the dedicated route:

- `/api/sora-api/video-gen/create`

Do not post arbitrary JSON to `/backend/video_gen` unless you also match the live Sora payload shape.

## Ready-to-use Script

```bash
python scripts/sora_video_create_and_wait.py \
  --api-key srk_xxx \
  --prompt "A cinematic shot of ocean waves at sunrise."
```

Optional flags:

- `--base-url http://127.0.0.1:1989`
- `--poll-interval 5`
- `--timeout 900`
- `--json`

## Quick Verification

If this command returns `200 OK`, the key is usable:

```bash
curl -X POST http://127.0.0.1:1989/api/sora-api/me \
  -H 'Authorization: Bearer srk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{}'
```
