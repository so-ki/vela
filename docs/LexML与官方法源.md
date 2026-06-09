# LexML 与官方法源 — 常见问题

## LexML 是什么？

**LexML Brasil**（https://www.lexml.gov.br/）是巴西联邦层面的**官方法律文献统一检索与标识系统**，由国会、司法部等公共机构维护，不是商业数据库。

- **URN**：每条法律有统一资源名，例如 LGPD：`urn:lex:br:federal:lei:2018-08-14;13709`
- **公开 HTTP**：可通过 `https://www.lexml.gov.br/urn/{URN}` 拉取官方 XML/HTML 文本
- **无需 API Key**：免费、公开，Vela 已内置 `lexml_fetch_service.py`

LexML 是**索引 + 标识**，Planalto（总统府）网站则常提供**法案全文 HTML**；STF/gov.br 各部委提供**判例与行政规则**。Vela 把它们组成「官方法源链」，而不是只依赖 LexML。

## 我现在就能用吗？

**可以。** 启动 Vela 后端后：

1. **协查主流程**：优先走本地语料；未命中时自动尝试 LexML URN 实时拉取；仍不足则给出 Planalto / STF / gov.br 门户链接。
2. **自检接口**（需登录法务账号）：
   ```bash
   curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/v1/legal/connector/status | python3 -m json.tool
   ```
   返回 `lexml_available_now` 与各官网站点 `endpoint_probes`。
3. **手动测 LexML URN**（无需 Vela）：
   ```bash
   curl -I "https://www.lexml.gov.br/urn/urn:lex:br:federal:lei:2018-08-14;13709"
   ```

**注意：**

- 从中国大陆访问 LexML / Planalto 可能**较慢或偶发超时**；MVP 以**本地 curated 语料**保证演示稳定，LexML 作增强而非唯一来源。
- **不需要**购买 Jusbrasil 等商业 API，也**不需要**巴西专用 MCP。
- 劳动合规请优先 **gov.br/trabalho-e-emprego**（CLT）；**previdencia** 偏社保/养老金，与劳动法互补。

## Vela 里的三层引证

| 层级 | 含义 |
|------|------|
| `corpus_verified` | 本地语料已索引，可 grounding |
| `lexml_live` | 通过 URN 从 LexML 实时拉官方文本 |
| `portal_link` | Planalto · STF · gov.br 等门户链接，须法务点开核对 |

配置文件：`backend/app/data/brazil_official_portals.json`
