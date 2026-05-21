# PLAN-007: 表达向量维度可自定义 + 关键词匹配引擎升级 — 实施计划

**文档编号:** PLAN-007
**对应 SPEC:** SPEC-006 (v1.1, 修复后)
**依赖:** PLAN-002（表达向量基础架构）、PLAN-005（daily_turn_count 固定信号）
**版本:** 1.0
**日期:** 2026-05-21
**作者:** 知惠 (zhihui)
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Phase 0: 环境准备与基线验证](#phase-0-环境准备与基线验证)
    - [Phase 1: `_ExpressionVector.__init__()` 重构 — 支持 dict-of-dict + keywords_path + synonyms](#phase-1-_expressionvector__init__-重构--支持-dict-of-dict--keywords_path--synonyms)
    - [Phase 2: 关键词匹配引擎重构 — jieba 分词 + 精确匹配 + 同义词 + 否定检测](#phase-2-关键词匹配引擎重构--jieba-分词--精确匹配--同义词--否定检测)
    - [Phase 3: inject_context() debug 逻辑同步升级](#phase-3-inject_context-debug-逻辑同步升级)
    - [Phase 4: 热加载命令 `/hermes-persona reload keywords`](#phase-4-热加载命令-hermes-persona-reload-keywords)
    - [Phase 5: 新建 keywords/*.json 文件 + 配置迁移脚本](#phase-5-新建-keywordsjson-文件--配置迁移脚本)
    - [Phase 6: 全量回归 + 新增测试验收](#phase-6-全量回归--新增测试验收)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| Phase | 内容 | 预估时间 |
|:---|:---|:---:|
| Phase 0 | 环境准备与基线验证 | 5 min |
| Phase 1 | `__init__()` 重构 — dict-of-dict + keywords_path + synonyms | 30 min |
| Phase 2 | 匹配引擎重构 — jieba + 精确匹配 + 同义词 + 否定检测 | 35 min |
| Phase 3 | inject_context() debug 逻辑同步升级 | 15 min |
| Phase 4 | 热加载命令 `/hermes-persona reload keywords` | 20 min |
| Phase 5 | 新建 keywords/*.json 文件 + 配置迁移 | 15 min |
| Phase 6 | 全量回归 + 新增测试验收 | 20 min |
| **合计** | | **~2 小时 20 分** |

### 阶段依赖关系

```
Phase 0 (基线)
    ↓
Phase 1 (__init__ 重构) ──── Phase 5 (keywords 文件) ── 可并行
    ↓
Phase 2 (匹配引擎重构) ──── 依赖 Phase 1 的 keywords 格式
    ↓
Phase 3 (debug 同步升级) ── 依赖 Phase 2 的新匹配引擎
    ↓
Phase 4 (热加载命令) ────── 依赖 Phase 1 的设计
    ↓
Phase 6 (全量回归 + 测试验收)
```

Phase 1 和 Phase 5 可并行开展。Phase 2 依赖 Phase 1 完成（需要新版 keywords 格式）。Phase 3 依赖 Phase 2。Phase 4 可并行于 Phase 2+3（但需 Phase 1 的设计确认）。Phase 6 依赖所有前置。

---

## 2. 实施步骤

### Phase 0: 环境准备与基线验证

**目标：** 确认分支正确、工作区干净、现有测试全量通过。

**操作：**

```bash
# 1. 确认分支（从 master 创建 feature 分支）
git branch --show-current
# 期望: feature/006-expression-vector-keywords 或类似

# 2. 确认工作区干净
git status
# 期望: 无未提交变更

# 3. 安装 jieba（新增依赖）
pip install jieba

# 4. 基线测试
python -m pytest tests/ -v
# 期望: 全量 PASSED, 0 failure
```

**验证标准：**
- `git branch --show-current` = `feature/006-expression-vector-keywords`
- `pip list | grep jieba` → 显示已安装
- `python -m pytest tests/ -v` → 全量通过

**回滚：** 无需回滚（尚未改动代码）

---

### Phase 1: `_ExpressionVector.__init__()` 重构

**目标：** 支持新配置格式（dict-of-dict），同时保持向后兼容旧格式（dict-of-list）。新增 `keywords_path` 外置文件解析和 `synonyms_path` 同义词加载。

#### 1a. `__init__()` 重构 — dimensions 解析

**文件：** `expression_vector.py`

**改动：**

```python
def __init__(self, cfg: dict, profile_path: str | None = None):
    # 1. 解析 dimensions（支持新/旧双格式）
    self.dimensions: dict[str, list[str]] = {}
    self.synonyms: dict[str, str] = {}  # 双向：src→dst, dst→src
    raw_dims = cfg.get("dimensions", {})
    
    for dim_name, dim_val in raw_dims.items():
        if isinstance(dim_val, list):
            # 旧格式：dict of list → 直接使用
            keywords = list(dict.fromkeys(str(k) for k in dim_val))
        elif isinstance(dim_val, dict):
            # 新格式：dict of dict → 解析 keywords / keywords_path
            keywords = self._resolve_dim_keywords(dim_name, dim_val, profile_path)
        else:
            continue  # 格式异常 → 跳过该维度
        self.dimensions[dim_name] = keywords
    
    # 2. 解析 synonyms（加载同义词映射）
    self._load_synonyms(cfg.get("synonyms_path"), profile_path)
    
    # 3. 解析 score_rules（优先维度内部，回退顶层）
    self.score_rules = self._resolve_score_rules(cfg, raw_dims)
    
    # ... 其余（reset_policy, storage_path, vectors 等）不变 ...
```

**新增方法：**

```python
def _resolve_dim_keywords(self, dim_name: str, dim_cfg: dict, profile_path: str | None) -> list[str]:
    """解析单个维度的关键词列表（支持内联+外置）。"""
    # keywords_path 优先
    path_val = dim_cfg.get("keywords_path")
    if path_val:
        try:
            kw_path = self._resolve_path(path_val, profile_path)
            if kw_path.is_file():
                data = json.loads(kw_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "keywords" in data:
                    return list(dict.fromkeys(str(k) for k in data["keywords"]))
        except (json.JSONDecodeError, OSError):
            pass  # 降级到内联 keywords
    
    # 降级：内联 keywords
    inline = dim_cfg.get("keywords", [])
    if inline:
        return list(dict.fromkeys(str(k) for k in inline))
    
    # 都没有 → 空关键词
    return []

def _load_synonyms(self, synonyms_path_val: str | None, profile_path: str | None) -> None:
    """加载同义词映射（双向）。"""
    self.synonyms = {}
    if not synonyms_path_val:
        return
    try:
        syn_path = self._resolve_path(synonyms_path_val, profile_path)
        if not syn_path.is_file():
            return
        data = json.loads(syn_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        # 构建双向映射
        for src, dst in data.items():
            src_s = str(src).strip()
            dst_s = str(dst).strip()
            if src_s and dst_s:
                self.synonyms[src_s] = dst_s
                self.synonyms[dst_s] = src_s  # 双向
    except (json.JSONDecodeError, OSError):
        pass

def _resolve_score_rules(self, cfg: dict, raw_dims: dict) -> dict[str, tuple]:
    """解析 score_rules：优先维度内部，回退顶层。"""
    top_rules = cfg.get("score_rules", {})
    default_rule = (1.0, -0.5, 1.0, 0.95)
    rules = {}
    
    for dim_name in self.dimensions:
        raw = None
        # 优先从维度内部读取
        dim_val = raw_dims.get(dim_name)
        if isinstance(dim_val, dict):
            raw = dim_val.get("score_rules")
        # 回退顶层
        if raw is None:
            raw = top_rules.get(dim_name)
        
        if isinstance(raw, (list, tuple)) and len(raw) >= 3:
            try:
                vals = [float(raw[0]), float(raw[1]), float(raw[2])]
                decay = float(raw[3]) if len(raw) >= 4 else 0.95
                rules[dim_name] = (vals[0], vals[1], vals[2], decay)
            except (ValueError, TypeError):
                rules[dim_name] = default_rule
        else:
            rules[dim_name] = default_rule
    return rules

def _resolve_path(self, path_val: str, profile_path: str | None) -> Path:
    """解析路径（支持 {profile} 占位符替换）。"""
    if profile_path and "{profile}" in path_val:
        path_val = path_val.replace("{profile}", str(profile_path))
    return Path(path_val).expanduser()
```

#### 1b. 验证测试

**文件：** `tests/test_expression_vector.py`（新增测试类）

**测试用例：**

| TC-ID | 场景 | 期望 |
|:---|:---|:---:|
| CFG-01 | 旧格式 dict-of-list → 兼容 | 关键词正确加载 |
| CFG-02 | 新格式 dict-of-dict（内联 keywords） | 关键词正确加载 |
| CFG-03 | 新格式（keywords_path 外置文件） | 从文件正确加载 |
| CFG-04 | keywords_path 文件不存在 | 降级空关键词 |
| CFG-05 | keywords_path + keywords 都没有 | 空关键词 |
| CFG-06 | synonyms 加载 + 双向映射 | 双向查找 |
| CFG-07 | synonyms_path 文件不存在 | 空映射，不抛异常 |
| CFG-08 | 混合：一些维度旧格式 + 一些新格式 | 各自正确解析 |
| CFG-09 | score_rules 维度内部优先 | 内部值覆盖顶层 |
| CFG-10 | score_rules 维度内部缺失→回退顶层 | 顶层生效 |

**验证标准：**
- 所有 CFG 测试通过
- 旧有 EV/RES/PERS/FMT 测试保持不变通过

**回滚：** `git checkout -- expression_vector.py` 回退文件

---

### Phase 2: 关键词匹配引擎重构

**目标：** 实现 jieba 分词流水线——预处理（分词→同义词展开→否定检测）→精确匹配。替换现有 `_count_keyword()` 方法。

#### 2a. 匹配流水线实现

**文件：** `expression_vector.py`

**改动：**

在 `_ExpressionVector` 类中新增/替换方法：

```python
# ── 新匹配引擎 ───────────────────────────────────────────────────

def _tokenize(self, text: str) -> list[str]:
    """分词：优先 jieba，降级空格/单字。"""
    if not text:
        return []
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        # 降级：英文按空格分，中文按字符分
        tokens = []
        for word in text.split():
            if word.isascii():
                tokens.append(word.lower())
            else:
                # CJK 字符逐个拆分
                for ch in word:
                    tokens.append(ch)
        return tokens

def _expand_synonyms(self, tokens: list[str]) -> list[str]:
    """同义词展开：对每个 token 添加同义词变体。"""
    if not self.synonyms:
        return tokens
    expanded = list(tokens)  # 保留原 tokens
    for token in tokens:
        if token in self.synonyms:
            expanded.append(self.synonyms[token])
    return expanded

def _detect_negation(self, tokens: list[str], kw_index: int, window: int = 3) -> bool:
    """否定检测：关键词所在 token 前 window 个 token 内是否有否定词。
    
    否定词表：不 / 没 / 别 / 无 / 不要 / 不用 / 没有
    窗口单位：token 级别，向前扫描 window 个 token。
    跨窗口或否定词不在窗口内 → 返回 False。
    """
    NEGATION_WORDS = {"不", "没", "别", "无", "不要", "不用", "没有", "别"}
    start = max(0, kw_index - window)
    for i in range(start, kw_index):
        if tokens[i] in NEGATION_WORDS:
            return True
    return False

def _match_keywords(self, tokens: list[str], keywords: list[str]) -> int:
    """精确匹配：对每个 keyword，检查是否在 tokens 中精确出现。
    
    返回命中次数（去重：同一 keyword 在同一消息中只计一次）。
    """
    hit_count = 0
    token_set = set(tokens)  # 精确匹配用 set
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        # 精确匹配：keyword 作为完整 token 出现
        if kw_lower in token_set:
            hit_count += 1
    return hit_count

def _match_keywords_with_negation(self, tokens: list[str], keywords: list[str]) -> int:
    """带否定检测的精确匹配。
    
    流程：
    1. 同义词展开 tokens
    2. 对每个关键词，在 tokens 中找到位置
    3. 检查位置前 window 个 token 内是否有否定词
    4. 无否定 → 计命中
    """
    if not tokens or not keywords:
        return 0
    
    # 同义词展开
    expanded = self._expand_synonyms(tokens)
    
    hit_count = 0
    token_set = set(expanded)  # 加速精确匹配
    
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        
        if kw_lower not in token_set:
            continue
        
        # 找到关键词在 expanded tokens 中的位置
        # 可能有多次出现，只要有一次不在否定区间内就计命中
        found_positive = False
        for idx, tok in enumerate(expanded):
            if tok == kw_lower:
                if not self._detect_negation(expanded, idx):
                    found_positive = True
                    break
        
        if found_positive:
            hit_count += 1
    
    return hit_count
```

**将 `update()` 中的 `_count_keyword()` 调用替换为：**

```python
# 替换 update() 中 L114-118：
# 旧：
# hit_count = sum(self._count_keyword(msg_lower, kw) for kw in keywords if kw)
# 新：
tokens = self._tokenize(user_message or "")
# 注意：tokenize 在循环外只做一次（不要对每个维度重复分词）
hit_count = self._match_keywords_with_negation(tokens, keywords)
```

需要调整 `update()` 的调用结构：`_tokenize` 在维度循环外执行一次，然后在每个维度的循环中调用 `_match_keywords_with_negation`。

```python
def update(self, user_message: str | None, session_id: str) -> None:
    snapshot_before = dict(self.vectors)
    if self.should_reset(session_id):
        self.vectors = {dim: 0.0 for dim in self.dimensions}
    
    # 一次性分词（所有维度共享）
    tokens = self._tokenize(user_message or "")
    
    for dim_name, keywords in self.dimensions.items():
        hit_score, miss_penalty, weight, decay_factor = self.score_rules[dim_name]
        self.vectors[dim_name] *= decay_factor
        
        # 新匹配引擎
        hit_count = self._match_keywords_with_negation(tokens, keywords)
        
        if hit_count > 0:
            self.vectors[dim_name] += hit_score * hit_count * weight
        else:
            self.vectors[dim_name] += miss_penalty * weight
        self.vectors[dim_name] = max(0.0, self.vectors[dim_name])
    
    # ... 其余不变（metadata, trace 日志）
```

#### 2b. 验证测试

**文件：** `tests/test_expression_vector.py`（新增测试类）

**测试用例：**

| TC-ID | 场景 | 期望 |
|:---|:---|:---:|
| MATCH-01 | 精确 token 匹配（英文 "PR" 不匹配 "process"） | 0 命中 |
| MATCH-02 | 精确 token 匹配（中文 "代码" 匹配 "写代码"） | 1 命中（"代码" 独立 token） |
| MATCH-03 | 否定检测（"不想抱抱" → intimacy 跳过） | 0 命中 |
| MATCH-04 | 否定检测（"没有Bug" → work 跳过） | 0 命中 |
| MATCH-05 | 否定检测（"抱抱" 无否定 → 命中） | 1 命中 |
| MATCH-06 | 同义词展开（synonyms: "推送"→"push"） | push 命中 work |
| MATCH-07 | 同义词双向（synonyms: "PR"→"pull request"） | "pull request" 命中 |
| MATCH-08 | 混合中英文（"修复 bug 写代码"） | work 命中 2 |
| MATCH-09 | jieba 不可用→降级分词 | 降级后仍能匹配 |
| MATCH-10 | 空消息/None 消息→全不命中 | 0 命中 |
| MATCH-11 | 全英文消息（jieba 分词英文效果） | 正确命中 |
| MATCH-12 | 同义词循环引用（A→B, B→A）| 不无限递归，正常返回 |
| MATCH-13 | 否定窗口跨边界（关键词在第一个 token）| 不抛异常，正常匹配 |
| MATCH-14 | 原 EV-14 子串匹配行为改变（"架构师"含"架构"）| 这取决于 jieba 分词结果→记录行为变化 |

**注意：** MATCH-14 是行为变更。旧引擎 `"架构师说".count("架构")` → 1（子串匹配）。新引擎 jieba 分词 `"架构师说" → ["架构师", "说"]` → `"架构"` 不在 token 中 → 0 匹配。**这是预期行为**（更精确），但需要通知用户关键词可能需要更新。

**验证标准：**
- 所有 MATCH 测试通过
- 原有 EV-01~14 测试按预期更新（可能需要调整 EV-14 测试期望值）
- 全量回归通过

**回滚：** `git checkout -- expression_vector.py`

---

### Phase 3: inject_context() debug 逻辑同步升级

**目标：** `inject_context()` 中 L1074-1077 的 debug 关键词命中检测逻辑需使用新分词引擎，而非旧的 `in` 子串匹配。

#### 3a. 替换 debug 关键词检测

**文件：** `injector.py`

**改动（L1064-1087）：**

```python
# 旧逻辑（L1074-1077）：
# for kw in ev.dimensions.get(dim_name, []):
#     if kw and kw.lower() in msg_lower:
#         hit_keywords.append(kw)
#         hit_count += 1

# 新逻辑：使用 ev._match_keywords_with_negation 的分词结果
# 但 debug 需要知道具体命中了哪些关键词（hit_keywords list）
# 方案：在 _ExpressionVector 中新增 _debug_get_hit_keywords() 方法

def _debug_get_hit_keywords(self, tokens: list[str], dim_name: str) -> tuple[list[str], int]:
    """返回 (命中关键词列表, 命中计数)，用于 debug 显示。"""
    keywords = self.dimensions.get(dim_name, [])
    if not tokens or not keywords:
        return [], 0
    
    expanded = self._expand_synonyms(tokens)
    token_set = set(expanded)
    hit_keywords = []
    
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower not in token_set:
            continue
        # 检查否定
        found_positive = False
        for idx, tok in enumerate(expanded):
            if tok == kw_lower:
                if not self._detect_negation(expanded, idx):
                    found_positive = True
                    break
        if found_positive:
            hit_keywords.append(kw)
    
    return hit_keywords, len(hit_keywords)
```

然后在 `inject_context()` 中：

```python
# 在 ev.update() 之后（L1064）
msg_lower = (user_message or "").lower()
debug_ev["enabled"] = True
debug_ev["turn_count"] = turn_count
for dim_name in sorted(ev.dimensions.keys()):
    old_val = snapshot_before.get(dim_name, 0.0)
    new_val = ev.vectors.get(dim_name, 0.0)
    delta = new_val - old_val
    # 使用新方法获取 hit_keywords
    hit_kws, hit_cnt = ev._debug_get_hit_keywords(tokens, dim_name)
    decay_dims = []
    if not hit_kws and delta != 0:
        decay_dims.append(dim_name)
    debug_ev["dimensions"][dim_name] = {
        "old": old_val,
        "new": new_val,
        "delta": delta,
        "hit_keywords": hit_kws,
        "hit_count": hit_cnt,
        "decay_dims": decay_dims if not hit_kws else [],
    }
```

**注意：** 这要求 `inject_context()` 在 `ev.update()` 之前得到 `tokens`。有两种方案：

方案 A：在 `ev.update()` 之前调用 `ev._tokenize()` 获取 tokens，然后将 tokens 传入 `ev.update()`（修改 update 签名）。
方案 B：在 `ev.update()` 之后调用 `ev._tokenize()` 再分词一次（轻量，~1ms）。

推荐 **方案 B**（不改 update 签名，兼容性强）。但如果性能敏感，可以在 `ev.update()` 内部返回 tokens。

#### 3b. 验证测试

**文件：** `tests/test_injector.py`（已有 debug detailed 测试中隐式验证）

**验证方式：**
- 修改 debug detailed 测试，验证 `hit_keywords` 使用新引擎（否定检测生效、子串不误命中）
- 手动构造消息 `"不想抱抱"`，验证 debug 输出中 intimacy 的 hit_keywords 为空

**验证标准：**
- debug detailed 测试通过
- 否定检测的 debug 输出正确

**回滚：** `git checkout -- injector.py`

---

### Phase 4: 热加载命令 `/hermes-persona reload keywords`

**目标：** 注册斜杠命令，支持热加载关键词文件。无需重启 Hermes。

#### 4a. 注册命令

**文件：** `__init__.py`

**改动：**

```python
# 在 register() 函数末尾新增
def register(ctx) -> None:
    # ... 现有代码 ...
    
    # 注册斜杠命令
    try:
        if hasattr(ctx, "register_command"):
            ctx.register_command(
                name="hermes-persona",
                handler=_handle_persona_command,
                description="管理 hermes-persona 插件",
                args_hint="<reload|keywords|status> [维度]"
            )
    except Exception:
        pass  # 命令注册失败不阻塞插件加载
```

**新增处理函数（在 `__init__.py` 或独立的 `commands.py`）：**

```python
# 推荐放在独立的 commands.py（保持 __init__.py 简洁）

# commands.py
"""Slash command handlers for hermes-persona."""

from __future__ import annotations

import json
from pathlib import Path

# 运行时访问 injector 模块状态
_HERMES_CONTEXT = None  # 由 register() 设置


def _handle_persona_command(args: str, user_message: str, **kwargs) -> str | None:
    """处理 /hermes-persona 命令。
    
    支持子命令：
    - reload keywords：热加载关键词和同义词文件
    - keywords <维度>：列出指定维度的当前关键词
    - status：显示当前表达向量状态
    """
    parts = args.strip().split()
    if not parts:
        return "用法: `/hermes-persona <reload|keywords|status> [维度]`"
    
    cmd = parts[0]
    
    if cmd == "reload":
        if len(parts) < 2 or parts[1] != "keywords":
            return "用法: `/hermes-persona reload keywords`"
        return _reload_keywords()
    
    elif cmd == "keywords":
        dim_name = parts[1] if len(parts) > 1 else None
        return _list_keywords(dim_name)
    
    elif cmd == "status":
        return _show_status()
    
    return f"未知子命令: {cmd}"


def _reload_keywords() -> str:
    """热加载关键词和同义词文件。
    
    通过设置一个全局标志，下一轮 inject_context() 会重新构造
    _ExpressionVector 实例并自动读取最新的关键词文件。
    """
    import injector
    # 设置重载标志
    injector._RELOAD_KEYWORDS = True
    return "✅ 关键词热加载已触发。下一轮对话将使用最新关键词。"


def _list_keywords(dim_name: str | None) -> str:
    """列出已加载的关键词信息。"""
    import expression_vector
    # 注：需要从运行时获取当前 _ExpressionVector 实例或其关键词数据
    # 由于 _ExpressionVector 在 inject_context() 内局部创建，
    # 最简单的方案是将当前实例缓存在 injector 模块级变量中
    
    # TODO: 依赖 Phase 3 完成后获取 ev 实例的方法
    return "📋 关键词列表（待实现 Phase 4 完善）"


def _show_status() -> str:
    """显示表达向量当前状态。"""
    # TODO: 同上，依赖 Phase 3
    return "📊 表达向量状态（待实现 Phase 4 完善）"
```

#### 4b. 模块级重载标志

**文件：** `injector.py` 模块级新增：

```python
# injector.py 顶部新增
_RELOAD_KEYWORDS: bool = False  # 热加载标志
```

然后在 `inject_context()` 的 expression_vector 处理部分：

```python
# 在创建 _ExpressionVector 之前（L1056-1058）
ev_cfg = config.get("expression_vector", {})
if _RELOAD_KEYWORDS and ev_cfg.get("enabled", False):
    _RELOAD_KEYWORDS = False  # 消费掉标志

# _ExpressionVector 的创建逻辑不变
ev = _ExpressionVector(ev_cfg, profile_path=profile)
```

#### 4c. 验证测试

**文件：** `tests/test_keywords.py`（新建）

**测试用例：**

| TC-ID | 场景 | 期望 |
|:---|:---|:---:|
| CMD-01 | reload keywords 无错误 | 返回成功信息 |
| CMD-02 | reload 后新关键词生效 | 旧关键词不匹配的消息在新加载后命中 |
| CMD-03 | status 命令 | 返回格式化状态 |
| CMD-04 | 未知子命令 | 返回错误信息 |
| CMD-05 | 无参数调用 | 返回用法信息 |

**验证标准：**
- 所有 CMD 测试通过
- 实际 Hermes 环境验证（可选，手动）

**回滚：** `git checkout -- __init__.py commands.py injector.py`

---

### Phase 5: 新建 keywords/*.json 文件 + 配置迁移

**目标：** 将现有 150+ 关键词从 `persona-config.json` 拆分到外置文件，创建同义词映射文件。

#### 5a. 创建 keywords 目录和文件

**目录：** `keywords/`（在项目根目录或 profiles 目录下）

**文件清单：**

```
keywords/
├── work.json          # work 维度关键词
├── intimacy.json      # intimacy 维度关键词
├── eros.json          # eros 维度关键词
├── play.json          # play 维度关键词
├── care.json          # care 维度关键词
├── future.json        # future 维度关键词
└── synonyms.json      # 同义词映射
```

**keywords/work.json：**
```json
{
  "keywords": [
    "代码", "架构", "Bug", "Debug", "PR", "测试", "重构",
    "修复", "commit", "push", "部署", "review", "git",
    "分支", "合并", "看板", "task", "CC", "工蜂", "子代理",
    "审查", "方案", "设计", "SPEC", "PLAN", "实现",
    "terminal", "ssh", "配置", "plugin", "hermes-persona"
  ]
}
```

**keywords/synonyms.json：**
```json
{
  "推送": "push",
  "PR": "pull request",
  "嗦粉": "吃饭",
  "世缘图": "世缘录",
  "抱抱": "hug",
  "亲亲": "kiss",
  "贴贴": "snuggle"
}
```

（其他维度文件按需求填充）

#### 5b. 更新 examples/persona-config.json

**文件：** `examples/persona-config.json`

将 `expression_vector.dimensions` 从 dict-of-list 改为 dict-of-dict，添加 `keywords_path` 和 `synonyms_path`。

**改动：**

```json
"dimensions": {
    "work": {
        "label": "工作投入",
        "keywords_path": "keywords/work.json",
        "score_rules": [1, -0.5, 1, 0.95]
    },
    "future": {
        "label": "未来愿景",
        "keywords_path": "keywords/future.json",
        "score_rules": [1, -1, 1, 0.95]
    },
    "intimacy": {
        "label": "亲密温度",
        "keywords": [],
        "score_rules": [1, -0.5, 3, 0.95]
    }
},
"synonyms_path": "keywords/synonyms.json"
```

#### 5c. 验证测试

**测试方式：**
- 手动验证配置加载：用新配置创建 `_ExpressionVector` 实例，验证关键词正确加载
- 路径解析测试：相对路径 `keywords/` 和绝对路径

**验证标准：**
- `_ExpressionVector` 能正确加载外置关键词文件
- 同义词双向映射正常工作
- 旧格式配置仍然兼容

**回滚：** 删除 keywords 目录，恢复 examples/persona-config.json

---

### Phase 6: 全量回归 + 新增测试验收

**目标：** 确保所有改动不破坏现有功能，且新功能完整可用。

#### 6a. 全量回归

```bash
python -m pytest tests/ -v
```

**期望：** 全量 PASSED，0 failure。

注意：需要检查以下测试是否因行为变更而需要调整：
- `test_expression_vector.py::TestUpdateAlgorithm::test_EV14_substring_match` — 子串匹配行为改变
- 其他关键词相关测试

#### 6b. 新增测试覆盖率

| 测试文件 | 测试类 | 覆盖范围 |
|:---|:---|:---|
| `test_expression_vector.py` | `TestConfigFormat` | CFG-01~10 |
| `test_expression_vector.py` | `TestMatchEngine` | MATCH-01~14 |
| `test_injector.py` | — | Debug hit_keywords 同步 (Phase 3) |
| `test_keywords.py` | `TestKeywordCommands` | CMD-01~05 |
| `test_keywords.py` | `TestKeywordsLoading` | 关键词文件加载、热加载 |

#### 6c. 手动验收检查清单

- [ ] 旧格式 `persona-config.json` 正常加载（无外置文件）
- [ ] 新格式 `persona-config.json` 正常加载（有外置文件）
- [ ] `"不想抱抱"` → intimacy 不上升
- [ ] `"process".count("PR")` → work 不上升（原误命中场景）
- [ ] `"推送代码到远端"` → work 上升（同义词命中）
- [ ] 中英文混合消息正常分词匹配
- [ ] `/hermes-persona reload keywords` 后新关键词立即生效
- [ ] `/hermes-persona status` 显示正常
- [ ] `/hermes-persona keywords work` 列出 work 维度关键词
- [ ] jieba 未安装时降级分词仍能匹配

#### 6d. 验收标准

- `python -m pytest tests/ -v` → 全量 PASSED
- 新增测试 ≥ 20 个（CFG 10 + MATCH 14 + CMD 5，减去重叠）
- SPEC-006 §2~§6 所有功能点测试通过

**回滚：** `git checkout master` 全量回退

---

## 3. 风险点与回滚方案

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---:|:---:|:---:|
| jieba 分词结果不符合预期 | 中 | 关键词匹配精度下降 | Phase 2 测试 MATCH-01~14 覆盖，手动验收 |
| jieba 首次 import 过慢 | 高 | pre_llm_call 首次延迟 >500ms | Phase 0 预导入 jieba；或延迟 import 到首次使用时 |
| 热加载命令 `ctx.register_command` 不存在 | 中 | 命令不生效 | `hasattr` 保护，兼容性检查 |
| 外置 keywords 路径解析失败 | 低 | 维度退场（空关键词） | Phase 1 的 _resolve_path 有 try/except |
| 旧测试 EV-14 子串匹配行为变更 | 必 | 测试失败 | 接受行为变更，更新测试期望值 |
| 大规模维度（>20）性能 | 低 | pre_llm_call 延迟增加 | 分词一次 + set lookup，O(n) 可控 |

### 回滚方案

**部分回滚（单一 Phase 失败）：**
```bash
git checkout -- <specific_file>.py   # 回退单个文件
```

**全量回滚：**
```bash
git checkout master                  # 放弃 feature 分支
git branch -D feature/006-expression-vector-keywords
```

**数据安全：**
- `expression_vector.json` 存储路径和格式不变 → 历史数据不受影响
- `persona-config.json` 改为新格式后旧格式仍有兼容层 → 降级可行

---

## 4. 验证检查清单

### 功能验证

- [ ] SPEC-006 §2.1: dict-of-dict 配置格式生效
- [ ] SPEC-006 §2.2: 外置 keywords/*.json 文件正确加载
- [ ] SPEC-006 §2.3: 同义词映射双向加载
- [ ] SPEC-006 §3.1: 完整流水线（分词→同义词→否定→匹配）
- [ ] SPEC-006 §3.2: `"PR"` 不匹配 `"process"`
- [ ] SPEC-006 §3.2: `"不想抱抱"` 不命中 intimacy
- [ ] SPEC-006 §3.2: `"推送"` 通过同义词命中 push
- [ ] SPEC-006 §3.3: 否定检测正确
- [ ] SPEC-006 §4.1: `__init__()` 直接加载关键词文件
- [ ] SPEC-006 §4.2: 热加载命令生效
- [ ] SPEC-006 §4.3: 回退链全部覆盖
- [ ] SPEC-006 §5: 三条命令均可用
- [ ] SPEC-006 §6: 旧格式兼容 + score_rules 双位置

### 代码质量

- [ ] `_ExpressionVector.__init__()` < 80 行（不含新增方法）
- [ ] 新增函数均有 docstring
- [ ] 所有 try/except 不吞没非预期异常（仅 OSError/JSONDecodeError/ImportError）
- [ ] 无新增全局变量（_RELOAD_KEYWORDS 单一例外）
- [ ] 测试覆盖所有回退路径
- [ ] 不破坏现有 inject_context() 的 fail-open 设计

---

## 附录 A：`expression_vector.py` 改动汇总

### 新增方法

| 方法 | 所在类 | 行数（估） |
|:---|:---|:---:|
| `_resolve_dim_keywords()` | `_ExpressionVector` | ~15 |
| `_load_synonyms()` | `_ExpressionVector` | ~20 |
| `_resolve_score_rules()` | `_ExpressionVector` | ~20 |
| `_resolve_path()` | `_ExpressionVector` | ~5 |
| `_tokenize()` | `_ExpressionVector` | ~15 |
| `_expand_synonyms()` | `_ExpressionVector` | ~8 |
| `_detect_negation()` | `_ExpressionVector` | ~10 |
| `_match_keywords()` | `_ExpressionVector` | ~12 |
| `_match_keywords_with_negation()` | `_ExpressionVector` | ~20 |
| `_debug_get_hit_keywords()` | `_ExpressionVector` | ~15 |

### 修改方法

| 方法 | 改动 |
|:---|:---|
| `__init__()` | 重写 dimensions/score_rules 解析逻辑 |
| `update()` | 替换 _count_keyword 为 _match_keywords_with_negation |

### 删除方法

| 方法 | 替代 |
|:---|:---|
| `_count_keyword()` | `_match_keywords_with_negation()` |

---

*🦊 知惠 执笔 · 2026-05-21 午间 · PLAN-007 基于 SPEC-006 v1.1（修复 C1+W1 后版本）*
