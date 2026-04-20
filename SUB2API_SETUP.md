# Sub2Api 部署记录

## 关键信息

- 项目目录: `/home/ubuntu/muxing/`
- 域名: `wenming-dev.org`
- Sub2Api 管理后台: `sub2api.wenming-dev.org`
- Cursor 专用入口: `cursor.wenming-dev.org`
- GitHub 用户: `wenming-ma`

## 架构

```
Cursor → 宿主机:8081 (cursor_proxy.py) → 容器:8080 (sub2api_core) → upstream
```

## 组件

### Sub2Api (Docker)

- 镜像: `weishaw/sub2api:latest` (当前版本 v0.1.114)
- 端口: 8080
- 配置: `data/config.yaml`

### cursor_proxy.py

轻量级反向代理（独立进程，跑在宿主机上），提供两个功能：

1. **reasoning_effort 注入** — 自动给请求加上 `"reasoning_effort": "xhigh"`
2. **reasoning_content 流式转换** — 把 `reasoning_content` delta 转换成带 emoji 的 `content` 输出

注意：array content 的转换（`[{"type":"text","text":"..."}]` → `"..."`）已在 v0.1.114 由 Sub2Api 自身修复，proxy 中的 `flatten_content` 已移除。

启动方式：
```bash
cd /home/ubuntu/muxing && nohup python3 cursor_proxy.py > data/logs/proxy.log 2>&1 &
```

日志: `data/logs/proxy.log`

### Cloudflared Tunnel

- 镜像: `cloudflare/cloudflared:latest`
- 通过 Cloudflare Tunnel 暴露服务到公网

## 数据库

- Neon PostgreSQL: `ep-wild-glitter-akm9jigw.c-3.us-west-2.aws.neon.tech`
- 注意: Neon 免费版有 compute time quota 限制，scheduler snapshot 和 usage cleanup 服务会因为配额超限报错，但不影响核心请求转发功能

## 模型信息

| 模型 | 上下文长度 |
|------|-----------|
| gpt-5.4 | 128K |
| gpt-5-pro | 272K |
| gpt-5-mini | 128K |
| gpt-5.4-mini | 128K |
| gpt-5.4-nano | 128K |

Codex/Cursor 配置中的 `model_context_window = 1000000` 是客户端本地设置，不是上游实际限制。

## 常见操作

### 重启 cursor_proxy.py
```bash
kill <PID>
cd /home/ubuntu/muxing && nohup python3 cursor_proxy.py > data/logs/proxy.log 2>&1 &
```

### 查看 docker 容器状态
```bash
docker ps -a
```

### 查看 Sub2Api 日志
```bash
tail -f data/logs/sub2api.log
```

## 已修复的问题

- v0.1.107: apicompat 中 system/tool 消息 array content 未支持的问题
- v0.1.112: Cursor /v1/chat/completions 发送 Responses API 格式 body 被静默丢弃的问题
- v0.1.114: outbox watermark 上下文过期导致 CPU 飙升的问题

## GitHub

https://github.com/wenming-ma/muxing