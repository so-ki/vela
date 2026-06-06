# 规则包目录 · 分类架构

## 层级

```
region（区域）
  └── country（法域 / 国家）
        └── rules_pack（协查规则包 JSON）
              ├── jurisdiction / industries / action_types
              ├── material_fields / checklist_items
              └── state_overlays
```

当前仅 **拉美 → 巴西 → `brazil_new_energy`** 一条活跃链路；新增法域时：

1. 在本目录添加 `{pack_id}.json`
2. 在 `index.json` 的 `regions` / `packs` 中登记
3. 无需改 `rule_engine` 核心逻辑（通过 `rules_registry.load_rules(pack_id)` 加载）

## 入口

| 文件 | 作用 |
|------|------|
| `index.json` | 区域 / 国家 / 规则包注册表与默认 pack |
| `brazil_new_energy.json` | 巴西 · 投资协查 v2.4 |

## API

- `GET /api/v1/rules/classification` — 区域 → 国家 → 默认 pack
- `GET /api/v1/rules/packs` — 已注册规则包列表
- `GET /api/v1/rules/catalog?pack_id=` — 指定 pack 的表单 / 清单配置（默认 pack 可省略参数）

## 场景存储

`investigation_scenarios.rules_pack_id` 记录创建时使用的规则包；为空时按 `country` 或默认 pack 解析（兼容旧数据）。
