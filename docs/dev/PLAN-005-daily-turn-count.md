# PLAN-005: turn_stage 改用每日总轮数 — 实施计划

**文档编号:** PLAN-005
**对应 SPEC:** SPEC-003 §2.5
**依赖:** US-002（`daily_turn_count` 固定信号 + JSON 持久化，已实现）
**版本:** 1.0
**日期:** 2026-05-20
**作者:** CC (Claude Code)
**审阅:** 知惠 & Kai.Xu
**状态:** 📋 待审阅

---

## 目录

1. [总体时间估算](#1-总体时间估算)
2. [实施步骤](#2-实施步骤)
    - [Phase 0: 环境准备与基线验证](#phase-0-环境准备与基线验证)
    - [Phase 1: 提取 _read_daily_turn_count()](#phase-1-提取-_read_daily_turn_count)
    - [Phase 2: injector.py 替换数据源](#phase-2-injectorpy-替换数据源)
    - [Phase 3: 回退逻辑与边界测试](#phase-3-回退逻辑与边界测试)
    - [Phase 4: 全量回归测试与验收](#phase-4-全量回归测试与验收)
3. [风险点与回滚方案](#3-风险点与回滚方案)
4. [验证检查清单](#4-验证检查清单)

---

## 1. 总体时间估算

| Phase | 内容 | 预估时间 |
|:---|:---|:---|
| Phase 0 | 环境准备与基线验证 | 5 min |
| Phase 1 | 提取 `_read_daily_turn_count()` | 15 min |
| Phase 2 | `injector.py` 替换数据源（L666） | 10 min |
| Phase 3 | 回退逻辑与边界测试 | 20 min |
| Phase 4 | 全量回归测试与验收 | 10 min |
| **合计** | | **~1 小时** |

### 阶段依赖关系

```
Phase 0 (基线) → Phase 1 (提取函数) → Phase 2 (替换数据源)
                                            ↓
                                      Phase 3 (回退测试)
                                            ↓
                                      Phase 4 (全量回归)
```

Phase 1~2 是连续改动链，不可并行。Phase 3 与 Phase 4 依赖 Phase 2 完成。

---

## 2. 实施步骤

### Phase 0: 环境准备与基线验证

**目标：** 确认分支正确、工作区干净、现有测试全量通过。

**操作：**

```bash
# 1. 确认分支
git branch --show-current
# 期望: feature/001-module-switch

# 2. 确认工作区干净
git status
# 期望: 无未提交变更

# 3. 基线测试
python -m pytest tests/ -v
# 期望: 全量 PASSED, 0 failure
```

**验证标准：**
- `git branch --show-current` = `feature/001-module-switch`
- `python -m pytest tests/ -v` → 全量通过，0 failure

**回滚：** 无需回滚（尚未改动代码）

---

### Phase 1: 提取 _read_daily_turn_count()

**目标：** 从 `_daily_turn_count_hint()` 中提取纯读取逻辑，形成只读、无副作用的 `_read_daily_turn_count()` 函数，用于给 `turn_stage` 提供跨会话累积轮数。

**文件：** `injector.py`

**位置：** 在 `_daily_turn_count_hint()` 之前（~L460）

**设计要点：**

- **只读、不递增**：与 `_daily_turn_count_hint()` 不同，此函数只读取当前计数，不执行 `count + 1` 也不写回 JSON
- **日期匹配检查**：若 JSON 中的 `date` 不是今天，返回 `0`（今天第一轮）
- **失败返回 None**：文件不存在、JSON 解析失败、OSError → 返回 `None`，由调用方决定回退策略

**新增函数（~30 行）：**

```python
def _read_daily_turn_count(profile_path: str = "") -> int | None:
    """读取当日累计轮数（只读、不递增），供 turn_stage 使用。

    从 daily_turn_count.json 读取跨会话累积的当日计数。
    与 _daily_turn_count_hint() 不同，此函数不执行递增和持久化。

    Args:
        profile_path: profile path for {profile} placeholder substitution.

    Returns:
        当日累计轮数（整数），读取失败返回 None。
        日期不匹配返回 0（今天尚无记录）。
    """
    from pathlib import Path
    import json

    # 读取配置获取 storage_path
    config = _load_config()
    fixed_cfg = config.get("fixed_signals", {})
    dc_cfg = fixed_cfg.get("daily_turn_count", {})
    if not dc_cfg.get("enabled", False):
        return None

    today_key = datetime.now().strftime("%Y-%m-%d")
    raw_path = dc_cfg.get(
        "storage_path",
        "~/.hermes/profiles/{profile}/state/daily_turn_count.json",
    )
    if profile_path:
        raw_path = raw_path.replace("{profile}", str(profile_path))
    storage_path = Path(raw_path).expanduser()

    try:
        if storage_path.is_file():
            saved = json.loads(storage_path.read_text(encoding="utf-8"))
            if isinstance(saved, dict) and saved.get("date") == today_key:
                return saved.get("count", 0)
            # 日期不匹配 → 今天尚无记录
            return 0
    except (json.JSONDecodeError, OSError):
        pass

    return None
```

**验证标准：**

```bash
# 1. 函数可导入
python -c "import injector; assert callable(injector._read_daily_turn_count); print('OK')"
# 期望: OK

# 2. daily_turn_count 未启用时返回 None
python -c "
import injector
with __import__('unittest.mock').patch('injector._load_config', return_value={}):
    assert injector._read_daily_turn_count() is None
print('OK')
"
# 期望: OK

# 3. 语法合法
python -c "import ast; ast.parse(open('injector.py').read()); print('OK')"
# 期望: OK
```

**回滚：**

```bash
git checkout HEAD -- injector.py
```

---

### Phase 2: injector.py 替换数据源

**目标：** 将 `inject_context()` 中 L666 的 `turn_count = len(conversation_history) // 2` 替换为优先使用 `_read_daily_turn_count()`，失败时回退到旧逻辑。

**文件：** `injector.py`

**位置：** `inject_context()` 函数内，约 L666

**当前代码（L666）：**

```python
turn_count = len(conversation_history or []) // 2
```

**改为：**

```python
# turn_count: 优先使用跨会话累积的每日轮数（US-002），
# 不可用时回退到会话内轮数
daily_count = _read_daily_turn_count(
    profile_path=kwargs.get("profile_path", "")
)
turn_count = (
    daily_count
    if daily_count is not None
    else len(conversation_history or []) // 2
)
```

**设计说明：**

| 场景 | `_read_daily_turn_count()` 返回 | `turn_count` 取值 |
|:---|:---|:---|
| US-002 已启用，今日已累积 N 轮 | `N` (int ≥ 0) | `N` |
| US-002 已启用，今日首轮（文件日期变化已归零） | `0` | `0` |
| US-002 已启用，文件尚不存在（首次运行） | `None` | `len(conversation_history) // 2` |
| US-002 未启用（`daily_turn_count.enabled=false`） | `None` | `len(conversation_history) // 2` |
| JSON 文件损坏 / OSError | `None` | `len(conversation_history) // 2` |

**阶段阈值映射不变：**

`_select_dynamic_rules()` → `_match_turn_stage()` 中：
- turn ≤ 5 → early
- turn ≤ 20 → mid
- turn > 20 → late

**验证标准：**

```bash
# 1. 语法合法
python -c "import ast; ast.parse(open('injector.py').read()); print('OK')"
# 期望: OK

# 2. 无 import 错误
python -c "import injector; print('OK')"
# 期望: OK

# 3. 确认旧逻辑仍存在于回退路径
grep -n "len(conversation_history" injector.py
# 期望: 有匹配（回退路径）
```

**回滚：**

```bash
git checkout HEAD -- injector.py
```

---

### Phase 3: 回退逻辑与边界测试

**目标：** 编写测试覆盖新数据源路径和回退路径，确保跨会话累积和降级行为正确。

**文件：** `tests/test_daily_turn_stage.py`（新建）

**测试用例清单（~10 个）：**

```python
"""Tests for turn_stage using daily_turn_count (SPEC-003 §2.5)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import injector


class TestReadDailyTurnCount:
    """_read_daily_turn_count() 单元测试。"""

    def test_enabled_returns_count(self):
        """daily_turn_count 启用且文件有效 → 返回计数。"""
        ...

    def test_disabled_returns_none(self):
        """daily_turn_count 未启用 → 返回 None。"""
        ...

    def test_no_file_returns_none(self):
        """存储文件不存在 → 返回 None。"""
        ...

    def test_date_mismatch_returns_zero(self):
        """文件 date 不是今天 → 返回 0。"""
        ...

    def test_corrupt_json_returns_none(self):
        """JSON 损坏 → 返回 None。"""
        ...


class TestTurnStageWithDailyCount:
    """turn_stage 使用 daily_turn_count 的集成测试。"""

    def test_daily_count_used_for_turn_stage(self):
        """_read_daily_turn_count 返回有效值 → turn_stage 基于每日轮数判断。"""
        ...

    def test_fallback_to_conversation_history(self):
        """_read_daily_turn_count 返回 None → 回退到 conversation_history 长度。"""
        ...

    def test_cross_session_count_accumulates(self):
        """跨会话累积：同一日内多次调用 → turn_stage 不退回 early。"""
        ...

    def test_daily_count_zero_early_stage(self):
        """每日轮数为 0 → turn_stage 为 early。"""
        ...

    def test_daily_count_after_100_late_stage(self):
        """每日轮数 > 20 → turn_stage 为 late。"""
        ...
```

**关键测试场景：**

| TC-ID | 场景 | 验证点 |
|:---|:---|:---|
| RDC-01 | US-002 启用，今日 42 轮 | `_read_daily_turn_count()` 返回 `42` |
| RDC-02 | US-002 未启用 | `_read_daily_turn_count()` 返回 `None` |
| RDC-03 | 文件不存在（首次运行） | 返回 `None`，回退到会话轮数 |
| RDC-04 | JSON 日期为昨天 | 返回 `0`（今天首轮） |
| RDC-05 | JSON 损坏 | 返回 `None`，回退 |
| TS-01 | daily_count=42 → turn_stage | 触发 after_100/after_200 规则（late 阶段） |
| TS-02 | daily_count=None → 回退 | `len(conversation_history) // 2` 正常运作 |
| TS-03 | 同一日内 3 次 `/new` | turn_stage 不退回 early |
| TS-04 | daily_count=0 | turn_stage=early（前 5 轮） |
| TS-05 | daily_count=100 | turn_stage=late（>20 轮） |

**操作：**

```bash
# 创建测试文件
touch tests/test_daily_turn_stage.py

# 运行新测试（预期：部分 FAIL 因 mock 需要调整，逐步修复至全部 PASS）
python -m pytest tests/test_daily_turn_stage.py -v
# 期望: ~10 passed
```

**验证标准：**
- 所有新测试 PASSED
- RDC-01~05 覆盖所有读取/回退路径
- TS-01~05 覆盖跨会话累积场景

**回滚：**

```bash
git checkout HEAD -- tests/test_daily_turn_stage.py
# 或直接删除
rm tests/test_daily_turn_stage.py
```

---

### Phase 4: 全量回归测试与验收

**目标：** 运行全部测试确认无回归，逐项验证验收标准。

#### 4.1 自动化测试

```bash
# 全量测试
python -m pytest tests/ -v

# 期望: 全部 PASSED，0 failure
# 新增 test_daily_turn_stage.py ~10 个测试全部通过
# 现有全部测试无回归
```

#### 4.2 验收检查清单

```bash
# AC-1: _read_daily_turn_count 函数存在并可用
python -c "import injector; assert callable(injector._read_daily_turn_count); print('PASS')"

# AC-2: inject_context() 中 turn_count 使用 daily_count 优先
grep -A3 "_read_daily_turn_count" injector.py | grep -q "turn_count" && echo "PASS" || echo "FAIL"

# AC-3: 回退路径保留（conversation_history 仍在代码中）
grep -q "conversation_history" injector.py && echo "PASS" || echo "FAIL"

# AC-4: _select_dynamic_rules() 签名不变
grep -q "def _select_dynamic_rules" dynamic_rules.py && echo "PASS"

# AC-5: _daily_turn_count_hint() 逻辑不变（不修改此函数）
python -c "
import ast, inspect
src = open('injector.py').read()
# 确认 _daily_turn_count_hint 的 count+1 逻辑仍在
assert 'count\"' in src or \"count'\" in src or '+ 1' in src
print('PASS')
"

# AC-6: 全量测试通过
python -m pytest tests/ -q
# 期望: 全部 passed in ...

# AC-7: 仅修改 injector.py + 新增测试文件
git diff --stat HEAD
# 期望: injector.py (少量行改动) + tests/test_daily_turn_stage.py (新建)
```

**影响范围确认：**

```bash
# 确认仅 injector.py 被修改（不含 dynamic_rules.py 等）
git diff --name-only HEAD
# 期望: injector.py + tests/test_daily_turn_stage.py（仅此二文件）
```

#### 4.3 手动冒烟测试

```python
# 模拟场景：daily_turn_count 已累积 42 轮
import json, tempfile
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory() as tmpdir:
    state_dir = Path(tmpdir) / "state"
    state_dir.mkdir()
    today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
    state_file = state_dir / "daily_turn_count.json"
    state_file.write_text(json.dumps({"date": today, "count": 42}))

    mock_config = {
        "fixed_signals": {
            "daily_turn_count": {
                "enabled": True,
                "storage_path": str(state_file),
            }
        },
        "dynamic": {
            "turn_stage": {
                "early": {"rules": []},
                "mid": {"rules": []},
                "late": {"rules": ["🦊 深度陪伴模式已激活"]},
            }
        },
    }

    with patch("injector._load_config", return_value=mock_config):
        count = injector._read_daily_turn_count()
        assert count == 42, f"Expected 42, got {count}"
        print(f"PASS: _read_daily_turn_count() = {count}")
```

**验证标准：**
- `_read_daily_turn_count()` 返回 `42`（不递增）
- `_daily_turn_count_hint()` 被调用后文件中的 count 变为 `43`（递增逻辑不受影响）

---

## 3. 风险点与回滚方案

### 3.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:--:|:--:|:---|
| `_read_daily_turn_count()` 每次调用都读磁盘，性能影响 | 低 | 低 | JSON 文件通常 < 100 bytes，`Path.read_text()` < 1ms；每日轮数场景下每轮调用一次，可接受 |
| `_read_daily_turn_count()` 与 `_daily_turn_count_hint()` 存在竞态（后者递增时前者读取） | 低 | 低 | 两个函数在同一线程内顺序调用（④a 固定信号 → ③ 动态规则），无并发问题 |
| 旧测试预期 turn_count 基于 conversation_history 长度，替换后可能失败 | 中 | 中 | `_read_daily_turn_count()` 默认返回 `None` 时走回退路径；需要确保测试中不意外触发 daily_turn_count 启用状态 |
| `_read_daily_turn_count()` 调用 `_load_config()` 可能递归或循环 | 低 | 低 | `_load_config()` 是幂等的文件读取函数，无副作用；`inject_context()` 中已调用一次，`_read_daily_turn_count()` 二次调用仅多一次文件读取 |
| 用户未配置 `fixed_signals.daily_turn_count` → 永久回退到旧逻辑 | 中 | 低 | 这正是设计意图：`daily_turn_count.enabled=false` 时返回 `None`，静默回退；若用户希望启用 turn_stage 每日轮数化，需同步启用 US-002 信号 |

### 3.2 回滚方案

| 回滚方式 | 操作 |
|:---|:---|
| **Git 回滚** | `git checkout HEAD -- injector.py` |
| **删除新测试** | `rm tests/test_daily_turn_stage.py` |
| **完整回滚** | `git stash` 或 `git reset --hard HEAD` |

### 3.3 安全边界

- `dynamic_rules.py` **完全未触碰** — `_select_dynamic_rules()` 签名不变
- `_daily_turn_count_hint()` **完全未触碰** — 递增/持久化逻辑不受影响
- `inject_context()` 注入顺序（①~⑦）不变
- 仅新增一个只读函数 + 替换一行赋值逻辑
- 回退路径保留 `conversation_history` 旧行为，fail-open

---

## 4. 验证检查清单

实施完成后的最终验收：

### 4.1 代码改动

- [ ] `_read_daily_turn_count()` 函数已添加到 `injector.py`
- [ ] `inject_context()` L666 处 `turn_count` 改用 `_read_daily_turn_count()` 优先
- [ ] 回退路径保留（`daily_count is not None else len(conversation_history) // 2`）
- [ ] `_daily_turn_count_hint()` 未修改
- [ ] `dynamic_rules.py` 未修改
- [ ] 只改动了 `injector.py` 一个源文件

### 4.2 测试

- [ ] `tests/test_daily_turn_stage.py` 新建，~10 个测试全部 PASSED
- [ ] `python -m pytest tests/ -v` → 全量通过，0 failure
- [ ] RDC-01~05 覆盖所有读取/回退路径
- [ ] TS-01~05 覆盖跨会话累积场景

### 4.3 行为验证

- [ ] US-002 启用时，turn_stage 基于跨会话每日轮数
- [ ] US-002 未启用时，静默回退到会话内轮数
- [ ] 日期变化后，每日轮数自动归零
- [ ] daily_turn_count.json 损坏时，不崩溃，回退到会话轮数

### 4.4 文件变更总览

| 文件 | 操作 | 说明 |
|:---|:---|:---|
| `injector.py` | 修改 | 新增 `_read_daily_turn_count()` + L666 数据源替换 |
| `tests/test_daily_turn_stage.py` | 新建 | ~10 个测试覆盖新路径和回退路径 |
| `dynamic_rules.py` | **不变** | 阶段映射逻辑不变 |
| 其他所有文件 | **不变** | 仅 injector.py 一处改动 |

---

*CC · 2026-05-20 · PLAN-005 v1.0（基于 SPEC-003 §2.5 · 依赖 US-002 已实现）· 等待审阅*
