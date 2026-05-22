# PLAN-010: 每日轮数来源过滤

> 日期：2026-05-22  
> 作者：知惠  
> 关联：SPEC-010 来源过滤  
> 分支：feature/001-module-switch

---

## 1. 当前状态

代码和配置已实现，待补充测试。

| 文件 | 状态 | 改动 |
|------|------|------|
| `injector.py` | 已实现 | `inject_context()` 第 1039-1044 行，+7 行黑名单过滤 |
| `persona-config.json` | 已实现 | `modules` 下加 `sources_blacklist` 列表 |
| `tests/test_sources_filter.py` | 未实现 | 新建，平台过滤单元测试 |

## 2. 任务拆分

### 任务 1：创建测试文件 `tests/test_sources_filter.py`

**目标**：验证 sources_blacklist 过滤逻辑的所有分支和边界情况。

**测试用例**（7 个）：

| # | 测试 | 场景 | 预期 |
|---|------|------|------|
| 1 | `test_cron_platform_filtered` | `platform="cron"`，`sources_blacklist` 含 `cron` | 只返回时间，不含规则/动态等 |
| 2 | `test_api_server_platform_filtered` | `platform="api_server"`，黑名单含 `api_server` | 同上 |
| 3 | `test_webhook_platform_filtered` | `platform="webhook"` | 同上 |
| 4 | `test_discord_platform_not_filtered` | `platform="discord"`，不在黑名单中 | 正常走完整流程，含时间+规则 |
| 5 | `test_unknown_platform_not_filtered` | `platform="new_platform"`，不在黑名单中 | 正常走完整流程（fail-open） |
| 6 | `test_blacklisted_time_disabled_returns_none` | `platform="cron"`，`modules.time=false` | `inject_context()` 返回 `None` |
| 7 | `test_no_sources_blacklist_backward_compat` | `sources_blacklist` 不在 modules 中 | 同未配置，不影响任何 platform |

**技术细节**：
- 使用 `patch("injector._load_config", ...)` 模拟配置输入
- 使用 `inject_context_defaults` fixture，覆写 `platform` 参数
- `conftest.py` 无需修改，现有 fixture 已满足需求

**验证方式**：
```bash
python -m pytest tests/test_sources_filter.py -v
```

### 任务 2：运行全量回归测试

**目标**：确认新增过滤逻辑不影响已有功能。

```bash
python -m pytest tests/ -v
```

**预期**：所有已有测试通过，无回归。

## 3. 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tests/test_sources_filter.py` | **新建** | 7 个测试用例 |
| `injector.py` | 不改动（已实现） | 黑名单过滤已在第 1039-1044 行 |
| `persona-config.json` | 不改动（已实现） | `sources_blacklist` 已在 modules 中 |
| `tests/conftest.py` | 不改动 | 现有 fixture 已满足需求 |

## 4. 不改动边界

以下文件和模块不受此功能影响，禁止改动：

- `guard.py` — 独立的安全护栏体系
- `dynamic_rules.py` — 过滤发生在 dynamic rules 之前，不影响其内部逻辑
- `expression_vector.py` — 同上
- `variance.py` — 同上
- `config.py` — 配置加载逻辑不变
- `pre_tool_call` / `post_tool_call` / `transform_llm_output` hooks

## 5. 验收清单

- [ ] `tests/test_sources_filter.py` 7 个测试全部通过
- [ ] `tests/` 全量测试无回归
- [ ] `platform="cron"` 命中黑名单 → 只返回时间上下文，不计数
- [ ] `platform="discord"` 不命中黑名单 → 正常走完整注入流程
- [ ] `sources_blacklist` 未配置时行为不变（向后兼容）
- [ ] `modules.time=false` 且黑名单命中 → 返回 `None`

## 6. 预估

| 任务 | 预估时间 |
|------|----------|
| 编写 7 个测试 | 15 分钟 |
| 运行全量回归 | 2 分钟 |
| **合计** | **~17 分钟** |
