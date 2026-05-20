# SPEC-005: 表达向量诊断增强 — 消息过滤 + 词边界匹配 + 衰减机制

**文档编号:** SPEC-005
**对应 US:** US-002 v1.0（表达向量与 FuzzyUtility 层 — 修复增强）
**版本:** 1.0
**日期:** 2026-05-20
**作者:** 知惠（Zhihui）
**审阅:** Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [概述](#1-概述)
2. [消息过滤](#2-消息过滤)
3. [关键词匹配修复](#3-关键词匹配修复)
4. [衰减机制](#4-衰减机制)
5. [Config Schema 变更](#5-config-schema-变更)
6. [代码改动清单](#6-代码改动清单)
7. [错误处理与兜底](#7-错误处理与兜底)
8. [测试策略](#8-测试策略)
9. [实施阶段拆分](#9-实施阶段拆分)
10. [审批检查清单](#10-审批检查清单)

---

## 1. 概述

### 1.1 目标

修复表达向量系统的三个叠加缺陷，消除 work 维度异常暴涨问题：

1. **消息过滤** — 后台进程完成通知被当作用户表达处理，导致 2000+ 字符的技术文档污染向量
2. **子串误命中** — `str.count()` 对短英文关键词（`PR` → `process`、`CC` → `account`）产生子串误匹配
3. **无衰减** — 向量值只涨不跌，一旦暴涨无法自然回落

同时修复关键词列表中存在重复条目的配置级问题。

### 1.2 范围

| 范围 | 说明 |
|:---|:---|
| **涉及** | `expression_vector.py`（过滤 + 词边界 + 衰减 + 去重）、`injector.py`（过滤调用点）、persona-config.json（`decay_factor` 字段）、测试文件补充 |
| **不涉及** | `dynamic_rules.py`、`guard.py`、`variance.py`、`plugin.yaml`、Hermes Agent 源码 |

### 1.3 术语表

| 术语 | 定义 |
|:---|:---|
| 后台消息 | 以 `[IMPORTANT: Background process` 为前缀的系统转发消息，包含 Claude Code 调用的命令和输出全文 |
| 词边界匹配 | `\bkeyword\b` 正则，确保 `PR` 不匹配 `process` |
| 衰减因子 | `decay_factor`，每轮先对向量执行乘法衰减再叠加命中/未命中 |

---

## 2. 消息过滤

### 2.1 问题

后台进程完成通知具备三个特征：长度极大（1000-2000+ 字符）、包含完整技术文档、以系统标记为前缀。它们不代表用户情绪/状态，但被 `update()` 当作普通用户消息处理，产生大量关键词命中。

### 2.2 判定规则

两条规则，**OR** 连接，命中任意一条即跳过表达向量处理：

**规则 A：子串匹配**

用户消息以 `[Kai.Xu]` 等发送者前缀开头，因此使用 `in` 子串包含判定而非 `startswith`：

```
"[IMPORTANT: Background process" in msg
```

**规则 B：长度 + 特征词密度**

```
len(msg) > 500 且 特征词命中数 ≥ 2

特征词列表: ["claude -p", "Command:", "Output:", "exit code"]
```

### 2.3 过滤位置

在 `injector.py` 的 `inject_context()` ④b 段，创建 `_ExpressionVector` 实例之前判定：

```python
if not _is_background_message(user_message or ""):
    ev = _ExpressionVector(ev_cfg, profile_path=profile)
    ev.load()
    ev.update(user_message or "", session_id)
    ev.save()
    parts.append(ev.format_inject(turn_count))
```

被过滤的消息不触发 `load()` / `update()` / `save()`，零 I/O 开销。

### 2.4 安全验证

基于实际会话数据（session `20260520_063548_1a1333e9`，82 条 user 消息）：

| 消息类型 | 数量 | 长度范围 | 误过滤风险 |
|---------|------|---------|-----------|
| 后台进程消息 | 6 | 1373-2113 | — |
| 正常用户消息 | 76 | 13-503 | **0 条命中** |

最长正常消息 503 字符，不含任何后台特征词。规则 A 的前缀 `[IMPORTANT: Background process` 是系统格式标记，用户不可能自然输入。

---

## 3. 关键词匹配修复

### 3.1 问题

`str.count()` 对短英文 ASCII 关键词产生子串误命中：

| 关键词 | 本意 | 误命中 |
|--------|------|--------|
| `PR` | Pull Request | p**r**ocess, app**r**oach, p**r**ogram |
| `CC` | Claude Code | a**cc**ount, a**cc**ept, su**cc**ess |
| `git` | Git | le**git**, di**git**al |
| `PLAN` | 实施计划 | **PLAN**NING, sup**plan**t |

### 3.2 判定逻辑

新增 `_count_keyword()` 方法，根据关键词类型自动选择匹配策略。

阈值 `len(keyword) <= 4` 的选择依据：
- 当前配置中已确认的问题关键词（`PR`、`Bug`、`push`）及同类短 ASCII 词（如 `CC`、`git`、`task`、`SPEC`、`PLAN` 等）长度集中在 2-5 字符
- 英文长度 ≥ 5 的关键词（如 `error`、`debug`、`server`）在当前配置中不存在，且子串误命中风险较低（`"error"` 仅会命中 `"terror"`、`"erroneous"` 等罕见词）
- 阈值为 4 是最小化行为变更的选择——只修复确认有问题的短词，其余保持现有行为

```python
def _count_keyword(self, text: str, keyword: str) -> int:
    if keyword.isascii() and len(keyword) <= 4:
        # 英文短词 → 词边界正则
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
        return len(pattern.findall(text))
    # 中文 / 长英文短语 → 子串匹配
    return text.count(keyword.lower())
```

### 3.3 命中示例

| 关键词 | 类型判定 | 匹配方式 | 文本 | 命中 |
|--------|---------|---------|------|------|
| `PR` | ASCII, len=2 | `\bPR\b` | `"review the PR please"` | 1 |
| `PR` | ASCII, len=2 | `\bPR\b` | `"process approach"` | 0 |
| `git` | ASCII, len=3 | `\bgit\b` | `"git push origin"` | 1 |
| `git` | ASCII, len=3 | `\bgit\b` | `"legitimate concern"` | 0 |
| `代码` | 中文 | `str.count()` | `"写代码"` | 1 |
| `hermes-persona` | ASCII, len=14 | `str.count()` | `"hermes-persona 插件"` | 1 |

### 3.4 关键词去重

在 `__init__` 加载维度关键词时自动去重：

```python
self.dimensions[dim_name] = list(dict.fromkeys([str(k) for k in keywords]))
```

消除配置中 `"修复"` 重复出现导致的重复计数。

---

## 4. 衰减机制

### 4.1 算法变更

`update()` 维度处理流程从：

```
命中？→ vector += hit_score * hit_count * weight
未命中 → vector += miss_penalty * weight → max(0.0, vector)
```

变为：

```
① vector *= decay_factor            ← 先衰减
② 命中？→ vector += hit_score * hit_count * weight
   未命中 → vector += miss_penalty * weight
③ max(0.0, vector)
```

衰减在命中/未命中之前执行，语义为"上一轮的印象随时间淡化，本轮新信号叠加其上"。

### 4.2 配置格式

`score_rules` 三元组扩展为四元组 `[hit_score, miss_penalty, weight, decay_factor]`：

```json
"score_rules": {
  "work":     [1, -0.5, 1, 0.95],
  "intimacy": [1, -0.15, 3, 0.95],
  "care":     [1, -0.5, 2, 0.95],
  "future":   [1, -1, 1, 0.95],
  "play":     [1, -1, 1, 0.95],
  "eros":     [1, -2, 5, 0.95]
}
```

- 默认值 `0.95`（旧格式三元组自动补齐）
- 范围建议 `0.85 ~ 1.0`
- `0.85` = 快速遗忘，`1.0` = 关闭衰减（旧行为）

### 4.3 效果示例（work=40，持续不命中，叠加 miss_penalty=-0.5）

| 轮数 | 无衰减 | 衰减 0.95 |
|------|--------|-----------|
| 当前 | 40.0 | 40.0 |
| +5 轮 | 37.5 | 28.7 |
| +20 轮 | 30.0 | 7.9 |
| +50 轮 | 15.0 | 0.0 |

衰减叠加未命中惩罚后，回落速度明显快于纯衰减。50 轮持续不命中后衰减组归零，而无衰减组仍有 15.0。

---

## 5. Config Schema 变更

### 5.1 score_rules 扩展

```json
{
  "expression_vector": {
    "enabled": true,
    "dimensions": { "..." : "..." },
    "score_rules": {
      "<dimension>": [
        <hit_score>,      // 命中时加分数，默认 1
        <miss_penalty>,   // 未命中扣分数，默认 -0.5
        <weight>,         // 权重乘数，默认 1
        <decay_factor>    // 🆕 每轮衰减因子，默认 0.95
      ]
    },
    "reset": "session",
    "storage_path": "..."
  }
}
```

向后兼容：代码读取时检查数组长度，三元组自动补 `decay_factor = 0.95`。

---

## 6. 代码改动清单

| 文件 | 改动 | 行数估算 |
|------|------|---------|
| `expression_vector.py` | ① `_is_background_message()` 函数 ② `_count_keyword()` 方法 ③ `update()` 中 L83-87 将 `msg_lower.count(kw.lower())` 替换为 `self._count_keyword(msg_lower, kw)`；添加衰减步骤（`vector *= decay_factor`） ④ `__init__` 解析 `decay_factor` + 去重 | ~40 行 |
| `injector.py` | ④b 段添加消息过滤判定；`from expression_vector import` 增加 `_is_background_message` | ~5 行 |
| `persona-config.json` | `score_rules` 四元组升级 | ~6 行 |
| `tests/test_expression_vector.py` | 消息过滤 / 词边界 / 衰减 / 去重 测试用例 | ~80 行 |

**共计 ~130 行改动，2 个源文件 + 1 个配置 + 1 个测试文件。**

---

## 7. 错误处理与兜底

延续现有 fail-open 原则：

| 场景 | 处理 |
|------|------|
| `_is_background_message()` 异常 | catch → 返回 False（视为正常消息，不阻塞） |
| `_count_keyword()` 正则编译失败 | catch → fallback `str.count()` |
| `decay_factor` 缺失 / 非法值 | 回退默认值 `0.95` |
| 旧格式三元组 | 自动补齐第四元 `0.95` |
| 磁盘 I/O 失败 | 静默降级（已有逻辑） |

---

## 8. 测试策略

### 8.1 单元测试

#### 新增测试

| 测试点 | 验证内容 |
|--------|---------|
| `_is_background_message` — 前缀命中 | `[IMPORTANT: Background process...` → True |
| `_is_background_message` — 密度命中 | 600 字符 + `claude -p` + `Command:` + `Output:` → True（≥2 个特征词出现） |
| `_is_background_message` — 密度边界 | 600 字符 + 恰好 2 个特征词（`claude -p` + `exit code`） → True |
| `_is_background_message` — 正常消息 | 正常对话文本 → False |
| `_is_background_message` — 特征词不足 | 600 字符但仅 1 个特征词 → False |
| `_count_keyword` — 英文短词边界 | `"process approach"` 不含 `"PR"` → 0 |
| `_count_keyword` — 英文短词命中 | `"review the PR please"` 含 `"PR"` → 1 |
| `_count_keyword` — 中文子串 | `"写代码测试"` 含 `"代码"` → 1 |
| `_count_keyword` — 长英文短语 | `"hermes-persona"` → 子串匹配 |
| 去重 | `["修复", "修复", "代码"]` → `["修复", "代码"]` |
| 衰减 | `decay_factor=0.5` → 一轮后半值；默认 `0.95` |
| 三元组向后兼容 | `[1, -0.5, 1]` → 自动补齐 `[1, -0.5, 1, 0.95]` |

#### 现有测试更新

衰减机制引入后，旧格式三元组自动补齐 `decay_factor=0.95`，现有测试中依赖具体向量数值的断言需要重新计算。涉及 `test_expression_vector.py` 中约 16 条直接断言 `ev.vectors["work"] == 具体数值` 的用例，需逐条验证并更新期望值。

### 8.2 集成测试

| 测试点 | 验证内容 |
|--------|---------|
| 后台消息不触发更新 | 注入上下文后，磁盘文件无变化 |
| 正常消息仍触发更新 | 注入上下文后，向量值按预期变化 |
| 完整注入链路 | `inject_context()` 返回的 context 字符串包含表达向量 |

---

## 9. 实施阶段拆分

| Phase | 内容 | 时间 |
|-------|------|------|
| 1 | `_is_background_message()` + injector.py 过滤调用 + 测试 | 15 min |
| 2 | `_count_keyword()` 词边界匹配 + 去重 + 测试 | 20 min |
| 3 | 衰减机制（update 流程 + config 解析 + 向后兼容）+ 测试 | 20 min |
| 4 | persona-config.json `score_rules` 四元组升级 | 5 min |
| 5 | 全量回归测试 + 手动验证 | 15 min |

**预估总计 ~1h15m。**

---

## 10. 审批检查清单

- [ ] 消息过滤规则是否覆盖所有已知后台消息格式
- [ ] 词边界匹配是否仅对 ASCII 短词（≤4 字符）生效
- [ ] 衰减机制是否向后兼容旧格式三元组
- [ ] fail-open 策略是否在所有新增路径上生效
- [ ] 测试用例是否覆盖关键边界条件
- [ ] persona-config.json 变更是否与示例配置同步
