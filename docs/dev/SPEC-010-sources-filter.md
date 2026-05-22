# SPEC-010: 每日轮数来源过滤

> 日期：2026-05-22  
> 作者：知惠  
> 状态：草稿  
> 关联：US-010 对话轮数精准计数

---

## 1. 问题

`daily_turn_count` 跨所有 Hermes 会话累积——包括 cron 任务（早报、晚报、SLM 维护、备份等），
导致每天的「轮数」远大于主人和知惠的真实对话轮数。

- 昨天（5/21）：`daily_turn_count` 显示 328 轮，但 Session DB 显示 Discord 对话约 80-90 轮，其余 200+ 是 cron
- `turn_stage` 阈值（after_100 / after_200）被 cron 任务提前触发，影响人格表达
- Cron 任务每轮都在注入完整 persona 上下文，浪费 token

## 2. 目标

**只对真人对话来源计入 daily_turn_count，cron 任务走精简注入流程（仅时间）。**

## 3. 方案

### 3.1 黑名单过滤

在 `inject_context()` 入口增加 **platform 黑名单**检查。

被过滤的 platform：
- `cron` — 定时任务
- `api_server` — API 服务
- `webhook` — Webhook 调用
- `msgraph_webhook` — MS Graph Webhook

### 3.2 配置

`persona-config.json` 的 `modules` 下新增字段：

```json
"sources_blacklist": ["cron", "api_server", "webhook", "msgraph_webhook"]
```

### 3.3 过滤逻辑

在 `inject_context()` 中，`_translate_mode` 判定后、数据容器初始化前插入：

```python
_sources_blacklist = modules.get("sources_blacklist", [])
if platform in _sources_blacklist:
    if _is_enabled(modules, "time"):
        return {"context": f"🕐 时间：{_weekday_cn}，{_current_time}"}
    return None
```

**行为**：
- 黑名单命中 → 只注入时间上下文，`_daily_turn_count_hint` 不被调用（**不计数**），跳过所有后续模块
- 黑名单未命中 → 照常走完整注入流程

### 3.4 为什么是黑名单而非白名单

主人要求：「把支持自然对话的平台都作为过滤备选」。Hermes 支持 21+ 个平台且持续增加。
维护白名单意味着每次新增平台都要改配置。

黑名单只需排除 4 个明确**非对话**来源 —— 其他所有平台（微信、飞书、Telegram、CLI 等）自动进入。

## 4. 改动文件

| # | 文件 | 改动 | 说明 |
|---|------|------|------|
| 1 | `injector.py` | +7 行 | 入口加黑名单过滤（第 1037 行后） |
| 2 | `persona-config.json` | +1 行 | `modules` 下加 `sources_blacklist` |
| 3 | `tests/test_sources_filter.py` | 新建 | 平台过滤单元测试 |

## 5. 不改动的文件

- `dynamic_rules.py` — 不受影响
- `expression_vector.py` — 不受影响
- `variance.py` — 不受影响
- `guard.py` — 不受影响
- `pre_tool_call` / `post_tool_call` / `transform_llm_output` hooks — 不受影响

## 6. 边界情况

| 场景 | 预期 |
|------|------|
| `sources_blacklist` 未配置（旧版配置） | `modules.get(..., [])` 返回 `[]`，不影响任何 platform |
| `sources_blacklist` 为空列表 | 同未配置 |
| `platform` 值不在 Hermes Platform 枚举中（动态平台） | 不被黑名单命中，正常走完整流程 |
| 早晚报 cron → Discord | `platform="discord"`，不命中黑名单，**放行**（主人确认问题不大） |
| 黑名单命中且 `modules.time=false` | 返回 `None`（无注入） |
| 黑名单命中且 `modules.time=true` | 返回 `{"context": "🕐 时间：周五，09:15"}` |

## 7. 验收标准

- [ ] `sources_blacklist` 配置在 persona-config.json 中生效
- [ ] cron 任务调用 `inject_context` 时只返回时间，不触发计数
- [ ] Discord 对话调用 `inject_context` 时正常走完整流程
- [ ] 未配置 `sources_blacklist` 时行为不变（向后兼容）
- [ ] 测试通过：新增 source 过滤测试 + 已有全量测试无回归

## 8. 参考

- Hermes Platform 枚举：`gateway/config.py:100-129`
- Session DB source 值：`cron, discord, cli, api_server, acp`
- 讨论记录：2026-05-22 晨间 Discord 对话
