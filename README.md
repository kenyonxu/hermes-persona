# hermes-agent-guide

> Hermes Agent 人设配置科普文章素材库 —— 以《崩坏：星穹铁道》翁法罗斯十三黄金裔为例

## 项目简介

本项目是 Hermes Agent（AI Agent 框架）人设配置系统的科普文章素材库。

我们选取米哈游《崩坏：星穹铁道》3.0 大版本「翁法罗斯」世界观中的**十三黄金裔**作为示例角色，将他们的游戏内设定翻译成 **Hermes Agent 的 persona / prefill 配置格式**，帮助读者理解：

- 什么是 AI Agent 的 "人设"（persona）
- 如何把虚构角色的性格、说话风格、价值观转化为机器可读的系统提示词
- persona 配置如何影响 Agent 的行为、语气、决策模式

## 目录结构

```
amphoreus-personas/
├── 00-overview.md          # 翁法罗斯世界观 & 十三黄金裔总览
├── 01-aglaea.md            # 阿格莱雅：领袖型 persona
├── 02-tribbie.md           # 缇宝：学者型 persona
├── 03-mydei.md             # 万敌：战士型 persona
├── 04-castorice.md         # 遐蝶：治愈型 persona
├── 05-anaxa.md             # 那刻夏：学者型 persona
├── 06-phainon.md           # 白厄：神秘型 persona
├── 07-cipher.md            # 赛飞儿：调皮型 persona
├── 08-cerydra.md           # 刻律德菈：领袖型 persona
├── 09-hyacine.md           # 风堇：治愈型 persona
├── 10-helektra.md          # 海瑟音：战士型 persona
├── 11-terravox.md          # Terravox
├── 12-cyrene.md            # 昔涟：神秘型 persona
├── 13-variables.md         # 三月七/丹恒：变量型 persona
├── persona-templates/      # Hermes Agent 配置文件模板
│   ├── prefill-aglaea.json
│   ├── prefill-mydei.json
│   └── ...
└── article-outline.md      # 科普文章大纲
```

## 数据来源

- 《崩坏：星穹铁道》游戏内文本、角色故事、语音
- 官方 HoYoLAB 文章与角色 PV
- [Honkai: Star Rail Wiki - Fandom](https://honkai-star-rail.fandom.com/)
- [萌娘百科 - 翁法罗斯](https://zh.moegirl.org.cn/翁法罗斯)

## 免责声明

本项目所有角色设定版权归米哈游（HoYoverse）所有，仅用于 AI Agent 技术科普目的，不作商业用途。

## License

MIT License — 配置文件模板与文档代码部分。
