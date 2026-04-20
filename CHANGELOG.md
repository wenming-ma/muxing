# cursor_proxy.py 变更记录

## v1.1 (2026-04-20)
- 移除 `flatten_content` 函数：array content 已由 Sub2Api v0.1.114 自行处理

## v1.0 (2026-04-09)
- 初始版本，包含以下功能：
  - `inject_reasoning`: 自动注入 `reasoning_effort: xhigh`
  - `fix_messages`: 转换 array content 为 string（后续移除）
  - 流式响应转换：`reasoning_content` delta → 带 emoji 的 `content`