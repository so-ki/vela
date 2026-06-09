#!/usr/bin/env python3
"""Append official gov.br reference links to brazil_legal_corpus.json."""
from __future__ import annotations

import json
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parents[1] / "backend/app/data/brazil_legal_corpus.json"

OFFICIAL_REF_ENTRIES = [
    {
        "id": "ref-planalto-legislacao-index",
        "source": "planalto-legislacao",
        "urn": "gov.br:planalto:legislacao",
        "url": "http://www4.planalto.gov.br/legislacao/",
        "title_pt": "Planalto — Legislação Federal",
        "title_zh": "Planalto 总统府 — 联邦与地方法规检索",
        "dimension": "foreign_investment",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["Planalto", "legislacao", "联邦法", "官方法案全文"],
        "checklist_codes": [],
        "text_pt": "Portal oficial do Planalto para consulta de leis, decretos, medidas provisórias e normas federais consolidadas.",
        "text_zh": "巴西总统府 Planalto 官方法规检索入口，可查联邦法律、法令等全文 HTML。",
    },
    {
        "id": "ref-stf-portal",
        "source": "stf",
        "urn": "gov.br:stf:portal",
        "url": "http://www.stf.jus.br/",
        "title_pt": "STF — Supremo Tribunal Federal",
        "title_zh": "STF 联邦最高法院 — 判决与法律信息",
        "dimension": "foreign_investment",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["STF", "判例", "宪法", "最高法院"],
        "checklist_codes": [],
        "text_pt": "Portal oficial do Supremo Tribunal Federal: jurisprudência, decisões e informações sobre controle de constitucionalidade.",
        "text_zh": "巴西联邦最高法院官方门户，可查宪法解释、重要判决与司法信息。",
    },
    {
        "id": "ref-stj-scon",
        "source": "stj",
        "urn": "gov.br:stj:scon",
        "url": "https://scon.stj.jus.br/SCON/",
        "title_pt": "STJ — Sistema de Consulta de Jurisprudência",
        "title_zh": "STJ 高等司法法院 — 判例检索",
        "dimension": "foreign_investment",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["STJ", "判例", "普通法"],
        "checklist_codes": [],
        "text_pt": "Sistema oficial de jurisprudência do Superior Tribunal de Justiça (STJ).",
        "text_zh": "巴西高等司法法院官方判例检索系统，补充 STF 宪法领域之外的判例。",
    },
    {
        "id": "ref-trabalho-govbr",
        "source": "trabalho",
        "urn": "gov.br:trabalho:portal",
        "url": "https://www.gov.br/trabalho-e-emprego/pt-br",
        "title_pt": "Ministério do Trabalho e Emprego",
        "title_zh": "劳动与就业部 — CLT 与雇佣合规",
        "dimension": "labor",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["CLT", "trabalho", "emprego", "劳动", "雇佣"],
        "checklist_codes": ["LAB-001", "LAB-002", "LAB-003"],
        "text_pt": "Portal oficial do Ministério do Trabalho e Emprego: legislação trabalhista, FGTS, convenções e orientações.",
        "text_zh": "巴西劳动与就业部官方门户，劳动法（含 CLT 相关）、雇佣合规与行政指南。",
    },
    {
        "id": "ref-previdencia-govbr",
        "source": "previdencia",
        "urn": "gov.br:previdencia:portal",
        "url": "https://www.gov.br/previdencia/pt-br",
        "title_pt": "Ministério da Previdência Social",
        "title_zh": "社会保障部 — 社保与养老金规则",
        "dimension": "labor",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["previdencia", "INSS", "社保", "养老金"],
        "checklist_codes": ["LAB-004"],
        "text_pt": "Portal oficial da Previdência Social: regras de contribuição previdenciária e benefícios (complementar à CLT).",
        "text_zh": "巴西社会保障部官方门户，社会保险与养老金规则（与 CLT 劳动雇佣法互补）。",
    },
    {
        "id": "ref-investsp-icms-incentivos",
        "source": "jusbrasil",
        "urn": "gov.br:investsp:incentivos-fiscais",
        "url": "https://www.investe.sp.gov.br/por-que-sao-paulo/incentivos-fiscais/",
        "title_pt": "InvestSP — Incentivos Fiscais do Estado de São Paulo",
        "title_zh": "InvestSP — 圣保罗州税收激励概览",
        "dimension": "tax",
        "level": "state",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["InvestSP", "ICMS", "Pró-Informática", "Pró-Veículo", "圣保罗", "激励"],
        "checklist_codes": ["TAX-002", "IND-008"],
        "text_pt": "InvestSP apresenta incentivos fiscais do Estado de São Paulo, incluindo programas de ICMS como Pró-Informática e Pró-Veículo para indústria e tecnologia. PRODEIC é programa de Mato Grosso, não de São Paulo.",
        "text_zh": "InvestSP 介绍圣保罗州税收激励，含 Pró-Informática、Pró-Veículo 等 ICMS 计划。PRODEIC 属于马托格罗索州，非圣保罗。",
    },
    {
        "id": "ref-sefaz-sp-beneficios",
        "source": "jusbrasil",
        "urn": "gov.br:sefaz-sp:beneficios-fiscais",
        "url": "https://portal.fazenda.sp.gov.br/acessoinformacao/Paginas/Beneficios-Fiscais.aspx",
        "title_pt": "Sefaz-SP — Benefícios Fiscais (ICMS)",
        "title_zh": "圣保罗州财政厅 — ICMS 官方优惠法令清单",
        "dimension": "tax",
        "level": "state",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["Sefaz", "ICMS", "benefício", "圣保罗", "优惠"],
        "checklist_codes": ["TAX-002"],
        "text_pt": "Portal da Secretaria da Fazenda do Estado de São Paulo lista benefícios fiscais de ICMS vigentes, condições e normas aplicáveis a investimentos industriais no estado.",
        "text_zh": "圣保罗州财政厅公开 ICMS 税收优惠清单及适用条件，供工业投资项目核查。",
    },
    {
        "id": "ref-campinas-alvara",
        "source": "jusbrasil",
        "urn": "gov.br:campinas:alvara-funcionamento",
        "url": "https://portal.campinas.sp.gov.br/secretaria/financas/pagina/alvara-de-funcionamento",
        "title_pt": "Prefeitura de Campinas — Alvará de Funcionamento",
        "title_zh": "坎皮纳斯市 — 营业执照（Alvará）申请指引",
        "dimension": "industry_access",
        "level": "municipal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["Campinas", "Alvará", "funcionamento", "市政", "许可"],
        "checklist_codes": ["IND-001"],
        "text_pt": "Guia municipal para obtenção do Alvará de Funcionamento em Campinas, requisito para operação de estabelecimentos comerciais e industriais.",
        "text_zh": "坎皮纳斯市营业执照（Alvará de Funcionamento）申请官方指引，工业设厂必备市政许可。",
    },
    {
        "id": "ref-campinas-zoneamento",
        "source": "jusbrasil",
        "urn": "gov.br:campinas:legislacao-urbanistica",
        "url": "https://portal.campinas.sp.gov.br/secretaria/planejamento-e-urbanismo/pagina/legislacao-urbanistica",
        "title_pt": "Campinas — Lei de Zoneamento e Uso do Solo",
        "title_zh": "坎皮纳斯市 — 城市规划与土地使用法规",
        "dimension": "industry_access",
        "level": "municipal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["Campinas", "zoneamento", "uso do solo", "规划", "用地"],
        "checklist_codes": ["IND-001"],
        "text_pt": "Legislação urbanística de Campinas: zoneamento, uso do solo e requisitos para implantação de empreendimentos industriais.",
        "text_zh": "坎皮纳斯城市规划与土地使用（Zoneamento/Uso do Solo）法规，工业用地须符合分区要求。",
    },
    {
        "id": "ref-anatel-certificacao",
        "source": "jusbrasil",
        "urn": "gov.br:anatel:certificacao-produtos",
        "url": "https://www.gov.br/anatel/pt-br/regulado/certificacao-de-produtos",
        "title_pt": "ANATEL — Certificação de Produtos",
        "title_zh": "ANATEL — 电信/电子产品认证与同源化指南",
        "dimension": "industry_access",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["ANATEL", "certificação", "telecom", "homologação", "认证"],
        "checklist_codes": ["IND-002", "IND-006", "IND-009"],
        "text_pt": "Agência Nacional de Telecomunicações: procedimentos de certificação e homologação de produtos de telecomunicações e equipamentos eletrônicos com conectividade.",
        "text_zh": "巴西国家电信局产品认证与同源化（homologação）官方指南，适用于通信及联网电子设备。",
    },
    {
        "id": "ref-aneel-outorgas",
        "source": "jusbrasil",
        "urn": "gov.br:aneel:outorgas",
        "url": "https://www.gov.br/aneel/pt-br/assuntos/outorgas",
        "title_pt": "ANEEL — Outorgas e Autorizações",
        "title_zh": "ANEEL — 电力许可与特许权申请指南",
        "dimension": "industry_access",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["ANEEL", "outorga", "储能", "grid", "并网", "特许"],
        "checklist_codes": ["IND-009"],
        "text_pt": "Agência Nacional de Energia Elétrica: outorgas, autorizações e procedimentos para geração, transmissão e armazenamento de energia conectado à rede.",
        "text_zh": "巴西国家电力局许可与特许权（Outorgas）申请官方指引，含储能并网相关程序。",
    },
    {
        "id": "ref-anpd-lgpd-guides",
        "source": "jusbrasil",
        "urn": "gov.br:anpd:documentos-publicacoes",
        "url": "https://www.gov.br/anpd/pt-br/documentos-e-publicacoes",
        "title_pt": "ANPD — Documentos e Publicações (LGPD)",
        "title_zh": "ANPD — LGPD 合规指南与自查清单",
        "dimension": "data_compliance",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["ANPD", "LGPD", "checklist", "Cookies", "DPO", "合规指南"],
        "checklist_codes": ["DAT-001", "DAT-002", "DAT-003"],
        "text_pt": "Autoridade Nacional de Proteção de Dados publica guias de conformidade LGPD, incluindo checklists para pequenas empresas, cookies, DPO e transferência internacional (Resoluções 15/18/19/2024).",
        "text_zh": "ANPD 官方 LGPD 合规出版物，含中小企业自查清单、Cookies 指南、DPO 职责及跨境传输配套规则。",
    },
    {
        "id": "ref-lgpd-lei-planalto",
        "source": "lexml",
        "urn": "urn:lex:br:federal:lei:2018-08-14;13709",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
        "title_pt": "Lei nº 13.709/2018 - LGPD (Planalto)",
        "title_zh": "LGPD 法案原文（Planalto 官方）",
        "dimension": "data_compliance",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2018-08-14",
        "tags": ["LGPD", "13709", "Planalto", "原文"],
        "checklist_codes": ["DAT-001", "DAT-002", "DAT-003"],
        "text_pt": "Texto oficial consolidado da Lei Geral de Proteção de Dados Pessoais (LGPD) no site Planalto.",
        "text_zh": "巴西总统府 Planalto 网站发布的 LGPD（Lei 13709/2018）官方法案全文链接。",
    },
    {
        "id": "ref-camex-resolucoes",
        "source": "jusbrasil",
        "urn": "gov.br:camex:resolucoes",
        "url": "https://www.gov.br/mdic/pt-br/assuntos/camex/resolucoes",
        "title_pt": "CAMEX — Resoluções GECEX (Comércio Exterior)",
        "title_zh": "CAMEX — 外贸委员会决议（关税/贸易救济）",
        "dimension": "industry_access",
        "level": "federal",
        "validity": "vigente",
        "published_at": "2025-01-01",
        "tags": ["CAMEX", "GECEX", "tarifa", "进口", "关税", "Reg Feed"],
        "checklist_codes": ["TAX-004", "IND-002"],
        "text_pt": "Resoluções do Conselho de Gestão do Comércio Exterior (CAMEX/GECEX) sobre tarifas, importação e medidas comerciais.",
        "text_zh": "外贸委员会 CAMEX/GECEX 决议发布页，跟踪关税调整与贸易救济措施。",
    },
]


def main() -> None:
    with open(CORPUS_PATH, encoding="utf-8") as f:
        corpus = json.load(f)

    existing = {s["id"] for s in corpus["sources"]}
    added = 0
    for entry in OFFICIAL_REF_ENTRIES:
        if entry["id"] in existing:
            continue
        corpus["sources"].append(entry)
        existing.add(entry["id"])
        added += 1

    # 更新已有 LGPD 条目的官方 URL
    for doc in corpus["sources"]:
        if doc.get("id") == "lexml-lei-13709-lgpd":
            doc["url"] = "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"

    parts = str(corpus.get("version", "1.4")).split(".")
    if len(parts) >= 2 and parts[-1].isdigit():
        parts[-1] = str(int(parts[-1]) + 1)
    corpus["version"] = ".".join(parts)

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Added {added} official refs; corpus v{corpus['version']}; total {len(corpus['sources'])}")


if __name__ == "__main__":
    main()
