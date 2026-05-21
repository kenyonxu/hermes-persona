"""Expression vector engine for the FuzzyUtility layer.

Multi-dimensional, self-decaying, user-controllable soft-prompt system.
Keywords match dimensions, scores accumulate/decay per turn, and the
current vector values are injected into LLM context each turn.
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger("hermes_tool_slimmer.expression_vector")


# ── 系统消息过滤 ───────────────────────────────────────────────────────────

_BG_MARKER = "[IMPORTANT:"
_BG_SIGNATURES = ["claude -p", "Command:", "Output:", "exit code"]
_BG_MIN_LENGTH = 500
_BG_SIGNATURE_THRESHOLD = 2


def _is_background_message(msg: str) -> bool:
    """判断是否为系统转发消息（不应计入表达向量）。

    规则 A：系统标记匹配 — 消息中包含 "[IMPORTANT:"（覆盖后台进程通知、
            skill 内容注入等所有系统转发消息）
    规则 B：长度 + 特征词密度 — len > 500 且 ≥ 2 个特征词命中
    OR 连接，命中任一规则返回 True。
    任何异常返回 False（fail-open）。
    """
    try:
        if _BG_MARKER in msg:
            return True
        if len(msg) > _BG_MIN_LENGTH:
            sig_hits = sum(1 for sig in _BG_SIGNATURES if sig in msg)
            if sig_hits >= _BG_SIGNATURE_THRESHOLD:
                return True
        return False
    except Exception:
        return False


class _ExpressionVector:
    """表达向量引擎：关键词匹配 → 累加/衰减 → 磁盘持久化 → 格式化注入。"""

    def __init__(self, cfg: dict, profile_path: str | None = None):
        # 1. 解析 dimensions — 支持旧格式(list)和新格式(dict of dict, SPEC-006)
        self.dimensions: dict[str, list[str]] = {}
        _dim_raw = cfg.get("dimensions", {})
        _dim_meta: dict[str, dict] = {}  # 暂存 dict 格式的元数据
        for dim_name, dim_val in _dim_raw.items():
            if isinstance(dim_val, list):
                # 旧格式: {"work": ["kw1", "kw2"]}
                self.dimensions[dim_name] = list(dict.fromkeys(str(k) for k in dim_val))
            elif isinstance(dim_val, dict):
                # 新格式 (SPEC-006): {"work": {"label": "...", "keywords": [...], "score_rules": [...]}}
                _dim_meta[dim_name] = dim_val
                keywords = dim_val.get("keywords", [])
                kp = dim_val.get("keywords_path", "")
                if kp:
                    # 外置关键词文件
                    kp_path = Path(kp)
                    if not kp_path.is_absolute():
                        kp_path = Path(__file__).resolve().parent / kp_path
                    try:
                        if kp_path.is_file():
                            data = json.loads(kp_path.read_text(encoding="utf-8"))
                            kw_list = data.get("keywords", [])
                            if isinstance(kw_list, list):
                                keywords = list(kw_list)
                    except (json.JSONDecodeError, OSError):
                        pass
                if isinstance(keywords, list) and keywords:
                    self.dimensions[dim_name] = list(dict.fromkeys(str(k) for k in keywords))

        # 2. 解析 score_rules — 优先维度内嵌 → 顶部旧格式 → 默认值
        self.score_rules: dict[str, tuple[float, float, float, float]] = {}
        default_rule = (1.0, -0.5, 1.0, 0.95)
        top_rules = cfg.get("score_rules", {})
        for dim_name in self.dimensions:
            # 优先：维度 dict 内的 score_rules
            dim_cfg = _dim_meta.get(dim_name, {})
            raw = dim_cfg.get("score_rules") if "score_rules" in dim_cfg else top_rules.get(dim_name)
            if raw is None:
                raw = list(default_rule)
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                try:
                    vals = [float(raw[0]), float(raw[1]), float(raw[2])]
                    decay = float(raw[3]) if len(raw) >= 4 else 0.95
                    self.score_rules[dim_name] = (vals[0], vals[1], vals[2], decay)
                except (ValueError, TypeError):
                    self.score_rules[dim_name] = default_rule
            else:
                self.score_rules[dim_name] = default_rule

        # 3. 重置策略
        self.reset_policy: str = cfg.get("reset", "session")
        if self.reset_policy not in ("session", "daily", "none"):
            self.reset_policy = "session"

        # 4. 存储路径（替换 {profile} 占位符）
        raw_path = cfg.get(
            "storage_path",
            str(Path(__file__).resolve().parent / "state" / "expression_vector.json"),
        )
        if profile_path:
            raw_path = raw_path.replace("{profile}", str(profile_path))
        self.storage_path: Path = Path(raw_path).expanduser()

        # 5. 初始化向量（全部 0.0）
        self.vectors: dict[str, float] = {dim: 0.0 for dim in self.dimensions}
        self._session_id: str | None = None
        self._last_updated: datetime | None = None

        # 6. 向量历史（最多 500 条）
        self.vector_history: deque[dict] = deque(maxlen=500)
        self._turn_counter: int = 0

    def update(self, user_message: str | None, session_id: str) -> None:
        """根据用户消息更新所有维度分数。"""
        # 0. 保存更新前快照（用于 trace 日志）
        snapshot_before = dict(self.vectors)

        # 1. 检查重置策略
        if self.should_reset(session_id):
            self.vectors = {dim: 0.0 for dim in self.dimensions}

        # 2. 逐维度处理
        msg_lower = (user_message or "").lower()
        for dim_name, keywords in self.dimensions.items():
            hit_score, miss_penalty, weight, decay_factor = self.score_rules[dim_name]

            # 比例衰减
            self.vectors[dim_name] *= decay_factor

            # 计算该维度关键词命中次数
            hit_count = sum(
                self._count_keyword(msg_lower, kw)
                for kw in keywords
                if kw  # 跳过空字符串
            )

            if hit_count > 0:
                self.vectors[dim_name] += hit_score * hit_count * weight
            else:
                self.vectors[dim_name] += miss_penalty * weight

            # 永不跌破 0
            self.vectors[dim_name] = max(0.0, self.vectors[dim_name])

        # 3. 更新元数据
        self._last_updated = datetime.now()
        self._session_id = session_id
        self._turn_counter += 1

        # 4. trace 日志：记录发生变化的维度
        if _logger.isEnabledFor(logging.DEBUG):
            changed_parts = []
            for dim_name in sorted(self.vectors):
                old_val = snapshot_before.get(dim_name, 0.0)
                new_val = self.vectors[dim_name]
                if old_val != new_val:
                    changed_parts.append(
                        f"{dim_name}: {old_val:.1f}→{new_val:.1f}"
                    )
            if changed_parts:
                msg_len = len(user_message) if user_message else 0
                _logger.debug(
                    "[EV] update: session=%s msg_len=%d → %s",
                    session_id,
                    msg_len,
                    " | ".join(changed_parts),
                )

    def _count_keyword(self, text: str, keyword: str) -> int:
        """根据关键词类型自动选择匹配策略。

        ASCII 短词（≤4 字符）→ \\b 词边界正则，避免子串误命中
        中文 / 长英文短语 → str.count() 子串匹配
        """
        try:
            if keyword.isascii() and len(keyword) <= 4:
                pattern = re.compile(
                    r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE
                )
                return len(pattern.findall(text))
            return text.count(keyword.lower())
        except Exception:
            # 正则编译失败 → fallback 子串匹配
            return text.count(keyword.lower())

    def should_reset(self, current_session_id: str) -> bool:
        """检查是否需要重置向量。"""
        if self.reset_policy == "none":
            return False

        if self.reset_policy == "session":
            if self._session_id is None:
                return False  # 首次加载不清零
            return current_session_id != self._session_id

        if self.reset_policy == "daily":
            if self._last_updated is None:
                return False
            return datetime.now().date() > self._last_updated.date()

        return False

    def load(self) -> None:
        """从磁盘加载向量状态。文件不存在或格式错误时保持初始值。

        旧默认路径 fallback（SPEC 4.3）：新路径不存在时尝试从旧默认路径
        ~/.hermes/expression_vector.json 读取，首次 save 时自然迁移到新路径。
        """
        try:
            load_path = self.storage_path
            if not load_path.is_file():
                _OLD_DEFAULT = Path("~/.hermes/expression_vector.json").expanduser()
                if _OLD_DEFAULT.is_file():
                    load_path = _OLD_DEFAULT
                else:
                    return

            data = json.loads(load_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return

            saved = data.get("vectors", {})
            for dim_name in self.dimensions:
                if dim_name in saved:
                    self.vectors[dim_name] = max(0.0, float(saved[dim_name]))

            self._session_id = data.get("session_id")
            ts = data.get("last_updated")
            if ts:
                self._last_updated = datetime.fromisoformat(ts)

            # 加载向量历史（向后兼容：旧数据无此字段时初始化为空）
            history_raw = data.get("vector_history")
            if isinstance(history_raw, list):
                self.vector_history = deque(history_raw, maxlen=500)
            else:
                self.vector_history = deque(maxlen=500)

            # 加载 turn_counter（向后兼容：旧数据无此字段时初始化为 0）
            self._turn_counter = int(data.get("turn_counter", 0))
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return

    def save(self) -> None:
        """将向量状态写入磁盘。创建父目录（如果不存在）。"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # 追加一条历史记录
            self.vector_history.append({
                "turn": self._turn_counter,
                "session_id": self._session_id,
                "time": datetime.now().isoformat(),
                "vectors": dict(self.vectors),
            })

            data = {
                "version": 1,
                "session_id": self._session_id,
                "last_updated": (
                    self._last_updated.isoformat()
                    if self._last_updated
                    else None
                ),
                "vectors": self.vectors,
                "turn_counter": self._turn_counter,
                "vector_history": list(self.vector_history),
            }
            self.storage_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 磁盘写入失败 → 静默降级

    def format_inject(self, turn_count: int) -> str:
        """格式化表达向量为注入文本。"""
        dim_parts = [
            f"{name}:{int(round(val))}"
            for name, val in sorted(self.vectors.items())
        ]
        dim_str = " ".join(dim_parts)
        return f"📊 [表达向量] {dim_str} | 第 {turn_count} 轮"

# ═══════════════════════════════════════════════════════════════════════════════
# SPEC-006: 关键词匹配引擎（jieba 分词 + 同义词扩展 + 否定检测）
# ═══════════════════════════════════════════════════════════════════════════════

_RELOAD_KEYWORDS = False

_NEGATION_WORDS = frozenset({
    "不", "没", "别", "无", "非", "否", "勿", "未", "莫",
    "没有", "不要", "不必", "不用", "并非", "从不", "绝不",
})

_DIMENSION_FILES = [
    "care.json",
    "eros.json",
    "intimacy.json",
    "play.json",
    "work.json",
    "future.json",
]

_SYNONYMS_FILE = "synonyms.json"


class _KeywordMatcher:
    """基于 jieba 分词的关键词维度匹配引擎（SPEC-006）。

    加载关键词词典文件，对用户消息进行分词、同义词扩展、否定检测，
    返回触发的维度列表。
    """

    def __init__(self, keywords_dir: Path) -> None:
        if not keywords_dir.is_dir():
            raise FileNotFoundError(f"Keywords directory not found: {keywords_dir}")

        self._keywords_dir = keywords_dir
        self._dimensions: dict[str, frozenset[str]] = {}
        self._synonym_map: dict[str, set[str]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._load_dimensions()
        self._load_synonyms()

    def _load_dimensions(self) -> None:
        dimensions: dict[str, frozenset[str]] = {}
        for filename in _DIMENSION_FILES:
            dim_path = self._keywords_dir / filename
            if not dim_path.is_file():
                continue
            dim_name = filename.replace(".json", "")
            try:
                data = json.loads(dim_path.read_text(encoding="utf-8"))
                keywords = data.get("keywords", [])
                if isinstance(keywords, list):
                    cleaned = frozenset(str(k).strip() for k in keywords if k)
                    if cleaned:
                        dimensions[dim_name] = cleaned
            except (json.JSONDecodeError, OSError):
                continue
        self._dimensions = dimensions

    def _load_synonyms(self) -> None:
        syn_path = self._keywords_dir / _SYNONYMS_FILE
        if not syn_path.is_file():
            self._synonym_map = {}
            return
        try:
            raw = json.loads(syn_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._synonym_map = {}
            return
        if not isinstance(raw, dict):
            self._synonym_map = {}
            return
        synonym_map: dict[str, set[str]] = {}
        for src, tgt in raw.items():
            src = str(src).strip()
            tgt = str(tgt).strip()
            if not src or not tgt:
                continue
            synonym_map.setdefault(src, set()).update({src, tgt})
            synonym_map.setdefault(tgt, set()).update({src, tgt})
        self._synonym_map = self._merge_synonym_clusters(synonym_map)

    @staticmethod
    def _merge_synonym_clusters(raw_map: dict[str, set[str]]) -> dict[str, set[str]]:
        if not raw_map:
            return {}
        words = list(raw_map.keys())
        word_to_idx = {w: i for i, w in enumerate(words)}
        parent = list(range(len(words)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for word, synonyms in raw_map.items():
            wi = word_to_idx[word]
            for syn in synonyms:
                if syn in word_to_idx:
                    union(wi, word_to_idx[syn])

        clusters: dict[int, set[str]] = {}
        for word, idx in word_to_idx.items():
            root = find(idx)
            clusters.setdefault(root, set()).add(word)

        result: dict[str, set[str]] = {}
        for word, idx in word_to_idx.items():
            result[word] = clusters[find(idx)]
        return result

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(self, user_message: str) -> list[str]:
        global _RELOAD_KEYWORDS
        if _RELOAD_KEYWORDS:
            self._load()
            _RELOAD_KEYWORDS = False

        if not user_message or not self._dimensions:
            return []

        tokens = self._tokenize(user_message)
        if not tokens:
            return []

        matched_dims: list[str] = []
        for dim_name, keywords in self._dimensions.items():
            if self._dimension_matches(tokens, keywords):
                matched_dims.append(dim_name)

        return matched_dims

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        try:
            import jieba
        except ImportError:
            return list(text)
        return [t.strip() for t in jieba.cut(text) if t.strip()]

    # ------------------------------------------------------------------
    # Dimension matching
    # ------------------------------------------------------------------

    def _dimension_matches(self, tokens: list[str], keywords: frozenset[str]) -> bool:
        raw_text = "".join(tokens)
        for i, token in enumerate(tokens):
            expanded = self._expand_token(token)
            for term in expanded:
                if term in keywords:
                    if not self._is_negated(tokens, i):
                        return True

            for kw in keywords:
                if len(kw) >= 1 and kw in token:
                    kw_pos = token.find(kw)
                    if self._token_prefix_has_negation(token, kw_pos):
                        continue
                    if not self._is_negated(tokens, i):
                        return True

        for kw in keywords:
            if len(kw) >= 2 and kw in raw_text:
                pos = raw_text.find(kw)
                token_idx = self._char_pos_to_token_idx(tokens, pos)
                if token_idx is not None and not self._is_negated(tokens, token_idx):
                    return True

        return False

    def _expand_token(self, token: str) -> set[str]:
        if token in self._synonym_map:
            return self._synonym_map[token]
        return {token}

    # ------------------------------------------------------------------
    # Negation detection
    # ------------------------------------------------------------------

    def _is_negated(self, tokens: list[str], keyword_idx: int, window: int = 2) -> bool:
        start = max(0, keyword_idx - window)
        for i in range(start, keyword_idx):
            token = tokens[i]
            if token in _NEGATION_WORDS:
                return True
            if self._is_general_negation_token(token):
                return True
        return False

    def _is_general_negation_token(self, token: str) -> bool:
        for neg in _NEGATION_WORDS:
            if token.startswith(neg):
                remainder = token[len(neg):]
                if not remainder:
                    return True
                for kw_set in self._dimensions.values():
                    if remainder in kw_set:
                        return False
                return True
        return False

    @staticmethod
    def _token_prefix_has_negation(token: str, kw_pos: int) -> bool:
        prefix = token[:kw_pos]
        for neg in _NEGATION_WORDS:
            if neg in prefix:
                return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _char_pos_to_token_idx(tokens: list[str], char_pos: int) -> int | None:
        offset = 0
        for idx, token in enumerate(tokens):
            if offset <= char_pos < offset + len(token):
                return idx
            offset += len(token)
        return None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> dict[str, frozenset[str]]:
        return dict(self._dimensions)

    @property
    def synonym_map(self) -> dict[str, set[str]]:
        return {k: set(v) for k, v in self._synonym_map.items()}
