# hermes-persona

> Agent 人格化方法论与插件工程——为 Hermes Agent 构建通用人格注入引擎

## 项目简介

`hermes-persona` 是一套完整的 Agent 人格化体系，包含三个层次：

| 层次 | 内容 | 产物 |
|:---|:---|:---|
| **方法论** | Lore→表达规则映射 + Prompt/Harness 双翼工程 | `docs/user-story-zhihui.md` |
| **插件** | `hermes-persona` Plugin——pre_llm_call 动态上下文注入 | `docs/hermes-persona-plugin-design.md` |
| **Spec** | 完整实现规格（即将启动） | `specs/` |

**核心创新**：将 Agent 人格化从「写一段提示词」（Prompt Engineering）提升为「设计一个注入系统」（Harness Engineering），利用 Hermes Agent 的 Plugin Hooks 实现每回合动态人格上下文注入。

## 文档索引

| 文档 | 定位 |
|:---|:---|
| [用户故事：知惠](docs/user-story-zhihui.md) | 8条Epic + 6场景 + 五章方法论 + 双翼架构 |
| [插件设计](docs/hermes-persona-plugin-design.md) | 通用代码架构 + 配置驱动 + 知惠示例 |
| [动态规则注入](docs/dynamic-rules-injection-design.md) | 时间/轮数/关键词三维动态人格适配 |
| [方法论文档](amphoreus-personas/) | 阿格莱雅案例 + 四步法 + 角色分类体系 |

## 快速开始

```bash
# 1. 安装插件
cp -r hermes-persona-plugin/ ~/.hermes/plugins/00-hermes-persona/

# 2. 创建配置
cat > ~/.hermes/profiles/<your-profile>/persona-config.json << 'EOF'
{
  "hermes-persona": {
    "context": {
      "rules": ["💬 你的自定义人格规则..."]
    }
  }
}
EOF

# 3. 重启 gateway
hermes gateway restart
```

## 许可

MIT License — 插件代码与文档。角色设定版权归原作者所有。

---

*🦊 知惠 & Kai.Xu · 2026-05-16*
