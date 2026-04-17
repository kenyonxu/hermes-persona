# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a documentation and research repository for Hermes Agent persona configuration. It uses characters from Honkai: Star Rail's "Amphoreus" setting as concrete examples to teach how fictional character personalities translate into machine-readable system prompts.

All documentation is in **Chinese**. The target framework is **Hermes Agent**, an AI Agent framework supporting MCP Server, Cron Jobs, and Webhooks.

## Repository Structure

```
amphoreus-personas/
├── 00-overview.md          # Worldview & all 13 Chrysos Heirs summary
├── raw-materials/          # Unprocessed source material (wiki scrapes, compiled notes)
├── designs/                # Architecture proposals and technical designs
│   └── 01-persona-craft-architecture.md  # Dynamic persona architecture (MCP Server + Cron + Webhook)
├── 01-aglaea.md ... 13-variables.md  # Planned per-character persona docs (not yet created)
├── persona-templates/      # Planned JSON prefill configs (not yet created)
└── article-outline.md      # Planned article outline (not yet created)
```

**Note**: This is an early-stage project. Only `00-overview.md` and Aglaea raw materials exist. The other 12 characters are planned but not yet written.

## Architecture (Persona Craft v0.1)

The `designs/01-persona-craft-architecture.md` proposes a zero-source-code-intrusion solution for dynamic persona management:

- **MCP Server**: Dynamic lore retrieval — injects character knowledge only when relevant
- **Cron Job**: Automated material maintenance (weekly wiki sync, lore diff reports)
- **Webhook**: External scene triggers — auto-switch active persona
- **Lore Store**: Local knowledge base (`raw-materials/`, `lore-cards/`, `personas/`)
- **Lightweight Prefill**: Minimal personality core split across `base.json` + `voice.json` + `secret.json`

## Data Sources

When researching character lore, use these sources:
- 《崩坏：星穹铁道》游戏内文本、角色故事、语音
- HoYoLAB Wiki (https://wiki.hoyolab.com/)
- Honkai: Star Rail Fandom Wiki (https://honkai-star-rail.fandom.com/)
- 萌娘百科 (https://zh.moegirl.org.cn/翁法罗斯)

## Conventions

- Character files follow the naming pattern `NN-character-name.md` (e.g., `01-aglaea.md`)
- Raw materials go in `raw-materials/<name>-raw.md` and `<name>-hoyolab-wiki.md`
- Each character doc should cover: identity, abilities, personality traits, signature quotes, relationships, and suitability for persona conversion
- The persona-template JSON format is not yet defined — reference the architecture doc for design principles

## No Build/Test System

This repository has no build system, test suite, or runnable application. It is pure Markdown documentation. Changes are validated by reading and cross-referencing for consistency.
