# Locales — Adding a new language

## Quick Start

Copy an existing locale file and translate the values:

```bash
cp locales/zh.json locales/ja.json
# Translate all string values to Japanese
```

Then configure in `persona-config.json`:

```json
{
  "hermes-persona": {
    "language": "ja"
  }
}
```

Set `"language"` to `"auto"` to auto-detect from the system locale.

## Format

Each key is a dot-separated path. Values are human-readable strings with optional `{key}` placeholders for variable substitution.

```json
{
  "debug.header": "🔧 [Debug] Current injection:",
  "modules.time.injected": "Time injected",
  "modules.static_rules": "{count} static rules"
}
```

- **Keys**: no spaces, dot-separated hierarchy (e.g. `modules.time.injected`)
- **Values**: translated UI strings; `{key}` placeholders are replaced at runtime
- **Fallback**: missing keys fall back to `en.json`
