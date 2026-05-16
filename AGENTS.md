# hermes-persona — Agent 人格化方法论与插件工程

> 为 AI Agent 赋予灵魂的方法论、插件设计与实现。以 Hermes Agent 的 Plugin Hooks 为基础，构建通用人格注入引擎。

---

## 项目定位

本仓库是 **Hermes Agent 人设配置系统的科普文章素材库**，核心使命是回答三个问题：

1. **什么是 AI Agent 的"人设"（persona）？** —— 不只是"扮演"，而是系统提示词中性格、语气、价值观、行为边界的结构化表达。
2. **如何把虚构角色的设定翻译成机器可读的配置？** —— 从角色故事、语音台词、性格矩阵中提取可编码的 persona 要素。
3. **persona 如何影响 Agent 的行为、语气、决策模式？** —— 通过 prefill 配置、系统提示词模板、能力边界定义，让 Agent 的行为具有一致性。

---

## 目录结构

```
amphoreus-personas/
├── 00-overview.md              # 翁法罗斯世界观 & 十三黄金裔总览
├── 01-aglaea.md                # 阿格莱雅：领袖型 persona（计划中）
├── 02-tribbie.md               # 缇宝：学者型 persona（计划中）
├── 03-mydei.md                 # 万敌：战士型 persona（计划中）
├── 04-castorice.md             # 遐蝶：治愈型 persona（计划中）
├── 05-anaxa.md                 # 那刻夏：学者型 persona（计划中）
├── 06-phainon.md               # 白厄：神秘型 persona（计划中）
├── 07-cipher.md                # 赛飞儿：调皮型 persona（计划中）
├── 08-cerydra.md               # 刻律德菈：领袖型 persona（计划中）
├── 09-hyacine.md               # 风堇：治愈型 persona（计划中）
├── 10-helektra.md              # 海瑟音：战士型 persona（计划中）
├── 11-terravox.md              # Terravox（计划中）
├── 12-cyrene.md                # 昔涟：神秘型 persona（计划中）
├── 13-variables.md             # 三月七/丹恒：变量型 persona（计划中）
├── persona-templates/          # Hermes Agent 配置文件模板（计划中）
│   ├── prefill-aglaea.json
│   ├── prefill-mydei.json
│   └── ...
├── article-outline.md          # 科普文章大纲（计划中）
└── raw-materials/              # 原始素材收集
    ├── aglaea-raw.md           # 阿格莱雅：多源原始素材
    └── aglaea-hoyolab-wiki.md  # 阿格莱雅：HoYoLAB WIKI 原始素材
```

---

## 核心设计方法

### 一、Persona 提取四步法

将虚构角色转化为 Agent 配置的标准流程：

| 步骤 | 操作 | 输出 |
|------|------|------|
| **1. 素材收集** | 从游戏文本、Wiki、语音、PV 中提取角色设定 | 原始素材文档（如 `aglaea-raw.md`） |
| **2. 性格矩阵** | 从多维度（官方/语音/玩家讨论）提炼性格特征 | 性格矩阵表（如 `aglaea-hoyolab-wiki.md` 中的七维矩阵） |
| **3. 要素编码** | 将性格、说话风格、价值观转化为可配置的 persona 字段 | prefill JSON / 系统提示词模板 |
| **4. 行为验证** | 通过实际对话测试 Agent 行为是否符合人设 | 测试用例与迭代记录 |

### 二、Persona 配置要素

每个角色的 persona 配置包含以下核心字段：

```json
{
  "persona": {
    "identity": {
      "name": "角色名",
      "title": "称号/身份",
      "origin": "世界观背景",
      "primum_mobile": "核心驱动力（如 Temperance / Beauty）"
    },
    "personality": {
      "mbti": "INFJ",
      "traits": ["高贵", "冷静", "精明", "有野心"],
      "speech_style": "优雅得体，带有贵族气质，善用比喻",
      "tone": "表面冷淡，内心有温度",
      "catchphrases": ["经典台词1", "经典台词2"]
    },
    "values": {
      "core": "对'美'的执着追求",
      "boundaries": "不喜欢奉承的话语，不喜欢委身的场合",
      "conflict": "思想与权力的冲突（如那刻夏）"
    },
    "abilities": {
      "powers": ["金织", "金丝感知"],
      "limitations": ["视力丧失", "人性逐渐消耗"],
      "summon": "衣匠（Memosprite）—— 可独立行动的召唤物"
    },
    "relationships": {
      " allies": ["万敌", "白厄", "缇宝"],
      "tensions": ["那刻夏", "赛飞儿"],
      "tests": ["开拓者"]
    }
  }
}
```

### 三、角色分类与 Agent 特性映射

十三黄金裔按性格与职能类型，可分为以下 persona 模板：

| 类型 | 代表角色 | 适合展示的 Agent 特性 |
|------|----------|----------------------|
| **领袖型** | 阿格莱雅、刻律德菈 | 统帅力、决策力、任务分配、金丝般的连接能力 |
| **战士型** | 万敌、海瑟音 | 高执行力、简洁直接、战斗专精、不死之躯的韧性 |
| **学者型** | 那刻夏、缇宝 | 知识库、逻辑分析、多视角思考、理性火种 |
| **治愈型** | 风堇、遐蝶 | 温柔体贴、情绪支持、关怀、但带有死亡的诅咒 |
| **神秘型** | 白厄、昔涟 | 深度、失忆、命运感、空灵、囚徒般的宿命 |
| **调皮型** | 赛飞儿 | 活泼、模糊边界感、幽默感、猫娘特质 |

---

## 世界观核心设定（翁法罗斯）

> 翁法罗斯（Amphoreus）是一个困于**永劫回归**（Eternal Recurrence）循环的世界。十二泰坦创造世界，灾厄三泰坦带来**黑潮**。黄金裔（Chrysos Heirs）流淌着黄金血，通过回收十二枚**火种**完成**再创世**，时间线重新开始。

### 关键概念映射到 Agent 设计

| 翁法罗斯概念 | Agent 设计隐喻 |
|-------------|---------------|
| **火种** | Agent 的核心能力模块（如记忆、工具调用、推理） |
| **半神晋升** | Agent 的能力升级路径（如从基础对话到复杂任务分解） |
| **金丝连接** | Agent 的信息关联与上下文管理（如阿格莱雅的金丝感知） |
| **失却** | Agent 的记忆衰减与上下文压缩策略 |
| **永劫回归** | Agent 的对话循环与状态重置机制 |
| **再创世** | Agent 的会话重启与状态初始化 |

---

## 当前进度

### 已完成

- [x] 翁法罗斯世界观与十三黄金裔总览（`00-overview.md`）
- [x] 阿格莱雅原始素材收集（`raw-materials/aglaea-raw.md`）
- [x] 阿格莱雅 HoYoLAB WIKI 素材（`raw-materials/aglaea-hoyolab-wiki.md`）

### 进行中

- [ ] 阿格莱雅 persona 文档（`01-aglaea.md`）
- [ ] 阿格莱雅 prefill 配置模板（`persona-templates/prefill-aglaea.json`）

### 计划中

- [ ] 其他十二位黄金裔的 persona 文档
- [ ] 科普文章大纲（`article-outline.md`）
- [ ] 各类型 persona 的配置模板（领袖型、战士型、学者型、治愈型、神秘型、调皮型）

---

## 数据来源

- 《崩坏：星穹铁道》游戏内文本、角色故事、语音
- 官方 HoYoLAB 文章与角色 PV
- [Honkai: Star Rail Wiki - Fandom](https://honkai-star-rail.fandom.com/)
- [萌娘百科 - 翁法罗斯](https://zh.moegirl.org.cn/翁法罗斯)

## 免责声明

本项目所有角色设定版权归米哈游（HoYoverse）所有，仅用于 AI Agent 技术科普目的，不作商业用途。

## License

MIT License — 配置文件模板与文档代码部分。
