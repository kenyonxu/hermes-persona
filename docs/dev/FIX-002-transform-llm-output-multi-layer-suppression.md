# FIX-002: transform_llm_output debug 块在流式推送平台不可见

**日期**: 2026-05-20  
**作者**: Kai.Xu  
**关联**: [FIX-001](./FIX-001-transform-llm-output-debug.md), [PR #29119](https://github.com/NousResearch/hermes-agent/pull/29119)

---

## 1. 现象

`transform_llm_output` hook 生成了 debug 摘要，persona 侧 trace 显示 SET → FOUND → appended 全链路正确，但终端用户（Discord、ACP 等流式平台）看不到任何 debug 输出。CLI 非流式路径正常。

## 2. 诊断过程

### 2.1 确认插件侧正确

在 `injector.py` 的 `inject_context` 和 `transform_llm_output` 两处加 `_trace()` 探针，写入 `/tmp/hermes_persona_trace.log`。每次对话都显示：

```
[inject_context]        SET   debug=True pending=203 chars
[transform_llm_output]  FOUND pending=203 chars → appended
```

结论：插件侧工作正常。

### 2.2 追踪 agent 侧数据流

通过逐层添加 TRACE 日志，发现三层 suppression（消息发送抑制）逐层拦截了已变换的 `final_response`：

| 层 | 位置 | 机制 | 影响 |
|----|------|------|------|
| **ACP** | `acp_adapter/server.py:1537` | `not streamed_message` guard | ACP 流式路径跳过发送 |
| **Gateway suppress** | `gateway/run.py:17578` | `_streamed or _content_delivered` 检查 | Discord 等平台抑制最终发送 |
| **Gateway run_sync** | `gateway/run.py:16939` | 构造返回 dict 时漏掉 `response_transformed` 字段 | 标记传递断链 |

关键证据来自 gateway TRACE 日志：

```
TRACE: final-send check transformed=False streamed=True content_delivered=True final_len=378
```

`transformed=False` 但 `final_len=378`（原始 175 + debug 203）——说明 debug 块已在 `final_response` 中，但标记没有传递到 gateway 判断点。

### 2.3 定位根因

`gateway/run.py` 的 `run_sync()` 函数（第 16939-16958 行）从 `run_conversation()` 返回的 result dict 中 cherry-pick 字段构造新的响应 dict，但**遗漏了 `response_transformed`**：

```python
# run_sync() 返回的 dict — 有 response_previewed，但没有 response_transformed
return {
    "final_response": final_response,
    ...
    "response_previewed": result.get("response_previewed", False),
    # response_transformed 缺失！
}
```

## 3. 修复方案

### hermes-persona 侧（本工程）

| 文件 | 修改 | 目的 |
|------|------|------|
| `injector.py` | 移除 `visible` 参数，统一 `_PENDING_DEBUG_BLOCK` 路径 | debug 启用即拼接 |
| `injector.py` | `_debug_summary()` 始终返回干净摘要 | 不再包裹 LLM 回显指令 |
| `injector.py` | 添加 `_trace()` 诊断探针 | 追踪 `_PENDING_DEBUG_BLOCK` 生命周期 |
| `__init__.py` | `sys.modules` 别名提前注册 | 修复扁平化后 `import config` 失败 |
| `injector.py` / `guard.py` | `parents[3]` → `parents[2]` | 扁平化后 fallback 配置路径修正 |

### hermes-agent 侧（fork: kenyonxu/hermes-agent）

| 文件 | 修改 | 目的 |
|------|------|------|
| `agent/conversation_loop.py` | `_response_transformed` 标记 + 传入 result dict | 告知下游响应被 hook 变换 |
| `gateway/run.py` `run_sync()` | 返回 dict 加入 `response_transformed` | 标记传递不断链 |
| `gateway/run.py` suppression 检查 | `transformed=True` 时编辑流式消息而非发新消息 | 避免重复消息 |
| `gateway/stream_consumer.py` | 暴露 `message_id` / `accumulated_text` 属性 | 支持原地编辑 |
| `acp_adapter/server.py` | 移除 `not streamed_message` guard | ACP 路径修复 |

## 4. 验证

```bash
# persona 侧
python -m pytest tests/ -v          # 232 passed

# 运行时验证
grep "TRACE: final-send check" agent.log
# transformed=True streamed=True → 不再 suppress
# transformed=False → 仅流式发送（无重复消息）
```

## 5. 影响范围

- `debug: false` 时完全无侵入，行为与未安装插件一致
- `debug: true` 时 debug 摘要通过编辑已有消息原地追加，不产生重复消息
- Discord / Telegram / ACP 等所有流式平台均受益
