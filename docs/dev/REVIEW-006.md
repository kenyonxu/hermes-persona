# REVIEW-006: SPEC-006 审查报告

**审查者:** 知惠 (zhihui)
**日期:** 2026-05-21 12:40
**审查范围:** `docs/dev/SPEC-006-expression-vector-customizable-keywords.md`

---

## 审查摘要

| 项目 | 结果 |
|------|------|
| 设计完整（五节） | ✅ 完整（配置/引擎/加载/命令/兼容性） |
| 技术可行 | ⚠️ 有 1 个 Warning |
| 兼容性 | ✅ 方案明确，但有 1 个 Warning |
| 回退链 | ❌ 1 个 Critical（`_KEYWORD_CACHE` 传递路径未定义） |
| 边界情况 | ⚠️ 有 2 个 Warning |

### 总计：1 Critical · 4 Warnings · 4 Suggestions

---

## CRITICAL（必须修复才能写 PLAN）

### C1. `_KEYWORD_CACHE` 传递路径未定义（§4.1）

**问题描述：**
SPEC §4.1 说「关键词和同义词存入模块级 `_KEYWORD_CACHE` dict，`_ExpressionVector` 实例化时从缓存取用，不重复读磁盘」。但当前代码中：

1. `inject_context()` (injector.py L1057) 调用 `_ExpressionVector(ev_cfg, profile_path=profile)`——构造函数直接从 `ev_cfg["dimensions"]` 读关键词，不经过任何缓存
2. `_ExpressionVector.__init__()` (expression_vector.py L54-57) 里 `self.dimensions` 直接从 cfg 解析
3. SPEC 没有定义 `_KEYWORD_CACHE` 在哪个模块声明、由谁填充、`_ExpressionVector` 怎么从缓存取数据

**影响：** 如果关键词外置到 `keywords/*.json`，新 `_ExpressionVector` 无法获取这些外置关键词。热加载后新实例也无法拿到刷新后的缓存。

**修复要求：**
- 明确定义 `_KEYWORD_CACHE` 的所有权（放在 `expression_vector.py` 模块级还是 `injector.py`）
- 定义谁负责加载外置文件并填充缓存
- 定义 `_ExpressionVector` 的构造接口是否新增 `keywords_cache` 参数
- 或改为在 `__init__()` 中直接解析 `keywords_path`（不经过缓存），这样最简洁

**建议修复方案（二选一）：**

方案 A（推荐·无需缓存层）：
- `_ExpressionVector.__init__()` 增加 keywords_path 解析逻辑（读取外置 JSON）
- 构造函数直接加载，不经过模块缓存
- 热加载通过重新构造 `_ExpressionVector` 实例实现

方案 B（缓存层）：
- `expression_vector.py` 增加模块级 `_KEYWORD_CACHE: dict` 和 `_LOADED_KEYWORD_PATHS: set`
- `_ensure_cache_loaded(path)` 辅助函数
- `_ExpressionVector.__init__()` 新增 `keywords_cache` 参数

---

## WARNINGS（需修复或明确说明）

### W1. `score_rules` 迁移路径不完整（§2.1 + §6）

**问题：**
旧格式 `score_rules` 是 `expression_vector` 的顶层字段；新格式 SPEC §2.1 将 `score_rules` 放入维度配置对象内部。但 SPEC §6 的兼容性迁移只说了 dimensions 格式的迁移，没涵盖 `score_rules` 的位置迁移。

当前 `_ExpressionVector.__init__()` L60-72 从 `cfg["score_rules"][dim_name]` 读取。新格式下，`score_rules` 从 `cfg["dimensions"][dim_name]["score_rules"]` 读取。迁移层需要同时处理这两种位置。

**修复要求：** 在 §6 中添加 `score_rules` 的迁移规则：优先读维度内部，读不到时回退顶层。

### W2. `inject_context()` 中 debug 关键词匹配逻辑与引擎不一致（injector.py L1074-1077）

**问题：**
`inject_context()` 在 L1074-1077 有独立的 debug 关键词命中检测：
```python
for kw in ev.dimensions.get(dim_name, []):
    if kw and kw.lower() in msg_lower:
        hit_keywords.append(kw)
        hit_count += 1
```
这个逻辑仍是裸子串匹配（`in` 操作），与 SPEC-006 的新分词引擎不一致。升级后 debug 信息中显示的 hit_keywords 会与真实的引擎命中不一致。

**修复要求：** 在 SPEC 或 PLAN 中说明 debug 逻辑需要同步升级——使用相同的分词/否定检测流水线来收集 hit_keywords。

### W3. 否定检测窗口单位模糊（§3.3）

**问题：**
§3.3 说「扫描窗口：关键词前 3 个 token」但 §3.1 预处理层的输出是 `tokens[] + 否定区间[]`。如果分词后 token 数量不定，「前 3 个 token」的长度在不同的分词粒度（英文单词 vs 中文字）下含义不同。

例如：
- `"我真的不想抱抱"` → jieba: `["我", "真的", "不想", "抱抱"]` → 否定词"不"在"抱抱"前 1 个 token
- `"推push推送"` → 混合文本分词结果不可预测

**修复要求：** 明确否定检测是在原始文本上做字符级扫描（关键词前 N 个字符），还是在 token 列表上做 token 级扫描（前 N 个 token）。建议：**原始文本字符级**（前 10 个字符），更简单稳定。

### W4. 斜杠命令注册接口未验证（§5.1）

**问题：**
§5.1 使用 `ctx.register_command(...)` 注册 `/hermes-persona` 斜杠命令。需要确认 Hermes `PluginContext` 是否存在 `register_command` 方法。如果不存在，需要改为其他机制（如工具注册）。

**修复要求：** 在 SPEC 中注明 `ctx.register_command` 的方法签名或改为先验证 Hermes ACP 接口再确定注册方式。

---

## SUGGESTIONS（建议性改进）

### S1. 建议统一定义 jieba 降级策略的实现细节（§4.3）

§4.3 说「jieba 不可用→回退空格分词（英文）或单字分词（中文）」。建议在 SPEC 中给出降级函数的伪代码或函数签名，特别是"单字分词"的具体实现——是按 unicode 字符逐个分割还是按 CJK 字符块分割。

参考实现：
```python
def _tokenize(text: str) -> list[str]:
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        # Fallback: split by whitespace for ASCII, char-by-char for CJK
        tokens = []
        for word in text.split():
            if word.isascii():
                tokens.append(word.lower())
            else:
                tokens.extend(word)  # char-by-char for Chinese
        return tokens
```

### S2. 建议明确标签和关键词的内联/外置优先级（§2.1）

§2.1 说关键词支持 `keywords`（内联）或 `keywords_path`（外置文件）。如果两者同时存在，谁优先？建议定义为 `keywords_path` 优先（外置覆盖内联），或者 `keywords` 优先（内联覆盖外置文件）。

### S3. 建议定义 `/hermes-persona status` 对新格式的输出格式

§5.2 的 `status` 命令输出当前六维值。新格式下维度数量可变，建议指定输出格式是按维度字母序展示所有维度值，或只展示非零维度。

### S4. 建议新维度的 `score_rules` 默认行为更明确

旧格式中缺失 `score_rules` 时使用默认 `[1, -0.5, 1, 0.95]`（L61）。新格式下新维度（无内联 score_rules 且无顶层回退）应使用同样的默认值。建议在 SPEC §2.1 或 §6 中明确说明。

---

## 设计完整性逐项检查

### 五节覆盖检查

| 节 | 内容 | 状态 | 备注 |
|:---|:---|:---:|:---:|
| §2 配置 | dimensions 格式、关键词文件、同义词文件 | ✅ | |
| §3 引擎 | 流水线（分词→同义词→否定→匹配） | ✅ | 否定检测单位需明确（W3） |
| §4 加载 | 加载时机、热加载、回退 | ⚠️ | C1（缓存传递路径缺失） |
| §5 命令 | 注册、命令列表 | ✅ | W4（接口验证） |
| §6 兼容 | 向后兼容、维度顺序无关、历史数据 | ⚠️ | W1（score_rules迁移不完整） |

### 技术可行性评估

`pre_llm_call` hook 的时间预算通常是 200-500ms。流水线性能估算：

| 阶段 | 预估耗时 | 说明 |
|:---|:---:|:---|
| jieba 分词（首次 import） | 200-500ms | 首次加载慢，后续快 |
| jieba 分词（后续调用） | 1-5ms | 短文本 |
| 同义词展开（10 条以内） | <0.1ms | dict lookup |
| 否定检测 | <0.1ms | token 扫描 |
| 精确匹配（10 维度 × 30 关键词） | <0.5ms | set lookup |
| **合计（首次）** | **~500ms** | 可接受边缘 |
| **合计（后续）** | **~10ms** | ✅ |

结论：**技术可行**。需要注意 jieba 首次 import 的预热问题——建议在注册时预导入 jieba。

### 回退链检查

| 失败场景 | SPEC 行为 | 评估 |
|:---|:---|:---:|
| `keywords_path` 文件不存在 | 降级用内联 `keywords` | ✅ |
| `keywords_path` + `keywords` 都没有 | 空关键词 | ✅ |
| `synonyms_path` 文件不存在 | 空映射 | ✅ |
| JSON 解析失败 | 降级同上 | ✅ |
| jieba 不可用 | 空格/单字分词回退 | ✅ 但建议更明确（S1） |
| 磁盘写入失败 | 静默降级（已实现） | ✅ |

### 边界情况检查

| 场景 | SPEC 覆盖 | 评估 |
|:---|:---:|:---:|
| 全零维度 | 未明确提及 | 兼容模式空 dimensions 应退化 |
| 单维度 | 隐式支持（dict 只有一个 key） | ✅ |
| 大量维度（>10） | 未明确提及 | 引擎遍历 dict 自动适配 |
| 中文+英文混合 | 隐式（jieba 可处理混合文本） | ✅ |
| 空 `keywords` 数组 | §4.1 说「空关键词」| ✅ |
| 同义词循环引用 | 未提及 | 如 A→B, B→A，展开时需防递归 |

---

## 结论

SPEC-006 整体设计完整，引擎流水线架构合理，技术可行。**存在 1 个 Critical 问题**（C1: `_KEYWORD_CACHE` 传递路径未定义），**4 个 Warning**（W1-W4）和**4 个 Suggestion**（S1-S4）。

**修复 C1 后即可进入 PLAN 阶段。** 建议按「修复 SPEC → 编写 PLAN」流程进行。
