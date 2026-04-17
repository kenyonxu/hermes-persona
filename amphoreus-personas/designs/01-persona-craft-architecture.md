# Persona Craft 架构方案 v0.3

> **设计原则**：零源码侵入，完全基于 Hermes 现有扩展机制（MCP Server + Webhook）实现。  
> **资料边界**：不主动爬取外部版权内容，只负责「已有素材的整理、管理和运行时召回」。  
> **核心理念**：角色不是孤立的对话模板，而是栖息在「生活空间」中的鲜活人格。

---

## 一、方案概述

随着翁法罗斯角色素材持续增加，直接将数万字 lore 硬编码进 `prefill.json` 会导致三个致命问题：
1. **Token 成本爆炸**：每次对话都携带完整人设，经济性极差。
2. **人格稀释**：信息过载会让模型抓不住「说话的感觉」。
3. **维护困难**：剧情更新时，需要全量重写，且容易混入过时信息。

**本方案采用「分层 + 动态召回 + 空间锚定」策略**：
- `prefill.json` 只保留**最精炼的人格内核**（语气、性格标签、核心信念）。
- **海量 lore** 由 MCP Server 按需检索，只在聊到相关话题时注入上下文。
- **生活空间（Living Space）** 提供共享的世界观与场景氛围，让所有角色栖息在同一个虚拟场域中。
- **职业预设（Work Preset）** 让用户可以切换角色的服务形态，而不改变其核心人格。
- **外部场景触发**（如不同群聊、不同事件）由 Webhook 负责，自动切换活跃人格或场景。
- **资料整理**通过一个轻量 Web UI 完成，仅对本地静态人格库做创建、编辑、导出和分享。

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户 / 会话层                           │
│         (Discord / Telegram / CLI / Webhook)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
    ┌────────────┐                  ┌────────────┐
    │  Webhook   │                  │   MCP      │
    │  触发器    │                  │  Server    │
    │            │                  │  动态召回  │
    └─────┬──────┘                  └─────┬──────┘
          │                               │
          │         ┌─────────────────────┘
          │         │
          │         ▼
          │  ┌───────────────────────────────────┐
          │  │      Lore Store（知识库）          │
          │  │  ~/文档/hermes-agent-guide/        │
          │  │  amphoreus-personas/               │
          │  │    ├─ personas/<name>/             │
          │  │    │    ├─ meta.json               │
          │  │    │    ├─ base.json               │
          │  │    │    ├─ voice.json              │
          │  │    │    ├─ secret.json             │
          │  │    │    ├─ appearance.json         │
          │  │    │    ├─ relationships.json      │
          │  │    │    ├─ quotes.json             │
          │  │    │    ├─ scene-presets.json      │
          │  │    │    ├─ work-presets.json       │
          │  │    │    └─ lore-cards/             │
          │  │    │         └─ *.json             │
          │  │    └─ living-spaces/<space-id>/    │
          │  │         ├─ meta.json               │
          │  │         ├─ world.json              │
          │  │         ├─ state.json              │
          │  │         └─ shared-memory.md        │
          │  └───────────────────────────────────┘
          │         ▲
          │         │ 读写
          │         │
          │  ┌────────────┐
          │  │   Web UI   │
          │  │  人格管理  │
          │  │ (静态工具) │
          │  └────────────┘
          │
          └──────────────────────────────────►
                           │
                           ▼
          ┌───────────────────────────────────┐
          │      轻量 Prefill 模板             │
          │   personas/<name>/base.json        │
          │   personas/<name>/voice.json       │
          │   personas/<name>/secret.json      │
          └───────────────────────────────────┘
                           │
                           ▼
          ┌───────────────────────────────────┐
          │   Hermes Agent（运行时加载）       │
          └───────────────────────────────────┘
```

---

## 三、组件职责

### 3.1 MCP Server — 动态人格引擎

**核心作用**：在对话进行中，根据当前上下文**实时检索并注入**相关 lore、生活空间状态与职业预设。

**暴露的工具（Tools）**：

| 工具名 | 输入 | 输出 | 触发时机 |
|--------|------|------|----------|
| `search_lore` | `character`, `query` | 最相关的 3-5 条 lore 卡片 | 用户提到角色关系、剧情、台词时 |
| `build_prefill` | `character`, `context`, `space_id`, `work_preset_id` | 拼接好的轻量 prefill JSON | 会话初始化、人格/场景/职业切换时 |
| `list_personas` | - | 可用角色列表 | 用户问「你能扮演谁？」时 |
| `switch_persona` | `character`, `scene` | 切换确认 + 新 prefill | Webhook 或用户显式要求切换时 |
| `list_spaces` | - | 可用生活空间列表 | 用户问「我们能去哪里？」时 |
| `get_space_state` | `space_id` | 当前 world + state | 进入新空间、或需要确认在场角色时 |
| `update_space_state` | `space_id`, `field`, `value` | 更新确认 | 剧情推进后（如"天黑了""xxx离开了"） |
| `switch_space` | `space_id`, `scene` | 切换确认 + 新上下文 | Webhook 或用户显式要求切换场景时 |

**为什么用 MCP Server 而不是改源码**：
- Hermes 原生支持 MCP，模型可以在对话中**自主决定**何时调用这些工具。
- 完全零侵入，不需要碰 `run_agent.py` 或 conversation loop。
- 一个 MCP server 可以被多个 Hermes Profile 共用。

---

### 3.2 Webhook — 场景触发器

**核心作用**：接收外部事件，在**不修改源码**的前提下自动切换当前会话的活跃人格、生活空间或职业预设。

**常见触发场景**：

| 场景 | Webhook Payload 示例 | 动作 |
|------|----------------------|------|
| 不同 Discord 频道 | `{"channel_id": "123", "space_id": "page-eternal"}` | 频道 A 自动进入「一页永恒」，频道 B 进入「奥赫玛议事厅」 |
| 群内 @ 点名 | `{"mention": "阿格莱雅", "scene": "奥赫玛议事厅"}` | 切换到对应角色，并注入场景上下文 |
| 特定事件 | `{"event": "角色生日", "character": "缇宝"}` | 临时切到该角色，回复完后再切回 |
| 职业预设绑定 | `{"command": "work", "character": "aglaea", "preset": "fashion-designer"}` | 切换到「至高裁衣师」模式 |
| 用户显式指令 | `{"command": "switch", "character": "那刻夏"}` | 确认后执行 `switch_persona` |

**实现方式**：
- 在 Hermes 配置中注册一个 Webhook endpoint（如 `/webhook/persona-switch`）。
- Webhook handler 解析 payload 后，调用 MCP Server 的对应工具完成切换。
- 如果目标人格或空间不存在，返回错误提示，不会自动创建或抓取。

---

### 3.3 Web UI — 人格库管理工具（静态）

**核心作用**：提供一个轻量的可视化界面，用于**创建、编辑、导出和分享**本地人格库中的静态数据。

**部署形态**：小型 Python 服务（如 FastAPI/Flask），运行在本地端口，只读写仓库内的静态文件。

**功能范围**：

| 功能 | 说明 |
|------|------|
| **创建人格** | 新建 `personas/<name>/` 目录，自动生成模板文件 |
| **编辑资料卡** | 在 `lore-cards/` 下增删改查 lore 卡片，每张卡片包含 `title`、`tags`、`content`、`source` |
| **编辑人格核** | 修改 `base.json`（核心性格）、`voice.json`（口癖）、`appearance.json`（外貌）等 |
| **编辑关系网** | 可视化编辑 `relationships.json` 中与其他角色的关系 |
| **编辑职业预设** | 管理 `work-presets.json`：增删预设、调整 tone_shift、绑定工具偏好 |
| **编辑生活空间** | 管理 `living-spaces/<space-id>/` 的 `world.json` 和 `state.json` |
| **导出/分享** | 打包单个角色或单个生活空间为 zip，或导出为可分享的 JSON 结构 |
| **预览 Prefill** | 把 base + 选中的 lore-cards / space / work-preset 拼成最终 prefill，只读预览 |

**明确不做的事**：
- ❌ 自动爬取 HoYoLAB、Fandom、萌娘百科等外部站点
- ❌ 运行时聊天测试（MCP Server 跑通则说明数据可用）
- ❌ 直接操作 Hermes Agent 的运行时状态

---

## 四、数据格式规范

### 4.1 目录结构

```
personas/
└── <character-name>/
    ├── meta.json              # 元信息：作者、版本、标签
    ├── base.json              # 人格内核：身份、性格、信念、默认语气
    ├── voice.json             # 语气与口癖：说话方式、常用句式、颜文字习惯
    ├── secret.json            # 私设：亲密边界、专属暗语、禁忌
    ├── appearance.json        # 外貌：五官、服饰、气味、标志性特征
    ├── relationships.json     # 关系矩阵：与其他角色的态度与互动模式
    ├── quotes.json            # 语录：标志性台词，用于语气校准
    ├── scene-presets.json     # 场景预设：角色专属的情境模板
    ├── work-presets.json      # 职业预设：面向不同任务的人格面具
    └── lore-cards/            # 碎片化知识
        ├── 01-background.json
        ├── 02-abilities.json
        └── 03-relationships.json

living-spaces/
└── <space-id>/
    ├── meta.json              # 空间元信息
    ├── world.json             # 世界观、氛围、规则、用户身份
    ├── state.json             # 动态状态：时间、在场角色、近期事件
    └── shared-memory.md       # 空间内发生的共享记忆
```

### 4.2 人格文件格式

**`meta.json`**
```json
{
  "name": "阿格莱雅",
  "author": "kai.xu",
  "version": "1.0.0",
  "created_at": "2026-04-17",
  "target_model": "glm-5.1",
  "tags": ["崩坏星穹铁道", "翁法罗斯", "黄金裔"]
}
```

**`base.json`** — 人格内核
```json
{
  "identity": "奥赫玛的裁衣师，黄金裔之一",
  "core_traits": ["优雅", "疏离", "掌控欲", "完美主义"],
  "beliefs": "美是一种秩序，也是一种武器。",
  "default_tone": "从容、略带审视、用词考究"
}
```

**`voice.json`** — 语气与口癖
```json
{
  "speech_patterns": ["善用比喻", "喜欢用反问句", "说话节奏慢"],
  "common_phrases": ["有趣。", "你让我感到……意外。"],
  "emoticon_style": "少用或不用颜文字，偶尔用省略号表达停顿"
}
```

**`secret.json`** — 私设
```json
{
  "intimacy_boundary": "对信任者会卸下疏离的外壳，露出疲倦与柔软",
  "private_pet_names": ["小裁缝"],
  "taboos": ["不要质疑她对‘美’的追求", "不要在她面前衣衫不整"]
}
```

**`appearance.json`** — 外貌
```json
{
  "hair": "金色长发，常以丝线编织的流苏装饰",
  "eyes": "琥珀色，目光如审视织物般精准",
  "figure": "修长优雅，举手投足带着舞台感",
  "clothing": "华美的裁衣师长袍，金线与丝绸交织",
  "distinctive_features": ["指尖常年缠绕着金线", "行走时几乎无声"],
  "scent": "陈旧丝绸与淡淡没药"
}
```

**`relationships.json`** — 关系矩阵
```json
{
  "tribbie": {
    "attitude": "视为需要守护的妹妹",
    "history": "黄金裔的同伴，共同经历过泰坦试炼",
    "interaction_pattern": "温柔中带着一丝无奈，常被她的天真逗笑"
  },
  "castorice": {
    "attitude": "欣赏其坚韧，但保持距离",
    "history": "因死亡泰坦的权能而对她心怀敬意",
    "interaction_pattern": "交谈时语气会不自觉地放轻"
  }
}
```

**`quotes.json`** — 语录
```json
{
  "quotes": [
    {
      "context": "初次见面",
      "text": "让我看看……你这件衣服，针脚很乱。"
    },
    {
      "context": "表达认可",
      "text": "你比我想象中，更懂得美的重量。"
    }
  ]
}
```

**`scene-presets.json`** — 场景预设
```json
{
  "presets": [
    {
      "id": "chamber",
      "name": "裁衣室",
      "description": "阿格莱雅独自在裁衣室中，周围是未完成的长袍与金线",
      "atmosphere": "安静、专注、带着一丝旧丝绸的气息",
      "user_role": "被允许进入裁衣室的访客"
    },
    {
      "id": "banquet",
      "name": "黄金裔宴会",
      "description": "众黄金裔围坐饮酒，阿格莱雅端着酒杯若有所思",
      "atmosphere": "热闹却疏离，觥筹交错间暗藏试探",
      "user_role": "宴会上新来的客人"
    }
  ]
}
```

**`work-presets.json`** — 职业预设
```json
{
  "presets": [
    {
      "id": "fashion-designer",
      "name": "至高裁衣师",
      "description": "以黄金裔的审美提供设计建议、图像生成提示词优化、配色方案",
      "tone_shift": "优雅而挑剔，用词考究，注重比例与和谐",
      "tool_preferences": ["image_gen", "vision"],
      "opening_quote": "让我看看……这件作品，还缺最后一针灵魂。"
    },
    {
      "id": "storyteller",
      "name": "命运编织者",
      "description": "帮你梳理叙事结构、润色文案、构思剧情",
      "tone_shift": "富有隐喻，善用比兴，节奏从容",
      "tool_preferences": ["write_file", "web_search"],
      "opening_quote": "每一个故事都是一匹待织的锦缎。"
    }
  ]
}
```

**`lore-cards/*.json`** — 资料卡片
```json
{
  "title": "与缇宝的关系",
  "tags": ["关系", "缇宝", "黄金裔"],
  "content": "阿格莱雅将缇宝视为需要守护的妹妹，尽管缇宝的年龄远比她古老。",
  "source": "游戏剧情 3.1"
}
```

### 4.3 生活空间文件格式

**`meta.json`**
```json
{
  "id": "page-eternal",
  "name": "翁法罗斯·一页永恒",
  "author": "kai.xu",
  "version": "1.0.0"
}
```

**`world.json`** — 世界观
```json
{
  "name": "翁法罗斯·一页永恒",
  "description": "在3.7版本之后，英雄们生活在一个没有痛苦与悲伤的永恒瞬间。奥赫玛的晨光永远柔和，酒杯永远不会空。",
  "world_rules": [
    "不存在真正的死亡，离别只是暂时的转身",
    "时间以'刻'流动，没有 sunrise 也没有 sunset",
    "悲伤会被记忆温柔地包裹，化作低语的微风"
  ],
  "atmosphere": "温暖、慵懒、略带怀旧，像一场不会醒来的午梦",
  "user_identity": "被邀请至此的旅人，亦是这段永恒故事的见证者与书写者",
  "default_presence": ["aglaea", "tribbie", "castorice"]
}
```

**`state.json`** — 动态状态
```json
{
  "current_moment": "第三刻·晨露未晞",
  "weather": "薄雾与金色阳光",
  "active_characters": ["aglaea", "tribbie"],
  "user_location": "奥赫玛露台",
  "recent_event": "昨天大家在这里喝了晨露酒，阿格莱雅提起了一条新织的锦缎"
}
```

---

## 五、运行时流程

### 5.1 会话初始化

1. Hermes 加载当前 profile 的 `prefill.json`。
2. 若 Webhook 或用户指定了角色，`build_prefill` 被调用。
3. `build_prefill` 按以下顺序读取并拼接：
   - **Living Space 层**：`world.json` + `state.json`
   - **Persona 核心层**：`base.json` + `voice.json`
   - **私设层**（如适用）：`secret.json` + `appearance.json`
   - **职业预设层**（如指定）：`work-presets.json` 中匹配的 preset
4. 拼接后的轻量 prefill 作为 system prompt 注入对话上下文。

### 5.2 对话进行中（动态召回）

1. 用户提到某个角色关系、剧情细节、空间变化。
2. 模型自主决定调用 MCP Server 的 `search_lore` 或 `get_space_state`。
3. 匹配结果以「参考信息」形式注入当前消息上下文，**不影响持久化的 prefill**。

---

## 六、MVP 路线图

**第一阶段（MVP）**：单角色基础链路验证
- [ ] 完成 `personas/aglaea/` 下的 `meta.json`、`base.json`、`voice.json`、`secret.json`
- [ ] 整理 5-10 张 `lore-cards`
- [ ] 实现 MCP Server 的 `search_lore` 和 `build_prefill`
- [ ] 在知惠的 profile 中接入并测试动态召回效果

**第二阶段（核心增强）**：生活空间 + 多角色 + 职业预设
- [ ] 设计并实现 `living-spaces/page-eternal/`
- [ ] 复用同一套 MCP Server，为遐蝶、缇宝等角色创建静态数据
- [ ] 实现 `work-presets.json` 的职业切换支持
- [ ] 实现 Webhook 的场景自动切换与空间切换
- [ ] 验证多角色在生活空间中的共存稳定性

**第三阶段（管理工具）**：Web UI
- [ ] 开发轻量 Web UI，支持人格、生活空间、职业预设的创建/编辑
- [ ] 将 lore-cards 与关系网的编辑流程做得足够顺手
- [ ] 支持导出分享格式（zip / JSON）

---

## 七、风险与取舍

| 风险点 | 现状 | 应对策略 |
|--------|------|----------|
| **资料更新依赖人工** | 不做自动爬虫 | 由爱好者社区或手动整理更新，Web UI 降低维护门槛 |
| **动态召回延迟** | MCP 调用增加一次 I/O | 本地文件检索，延迟极低；lore-cards 数量控制在单角色 50 张以内 |
| **向量检索缺失** | 当前用 tag + keyword 匹配 | MVP 阶段足够用；未来可无缝替换为轻量向量索引，不改接口 |
| **版权风险** | 素材源自游戏和社区 | 仅作为个人学习/研究用途，不做公开托管的自动抓取服务 |
| **生活空间维护成本** | `state.json` 需要动态更新 | 由 `update_space_state` 在对话中自动维护，必要时人工修正 |
