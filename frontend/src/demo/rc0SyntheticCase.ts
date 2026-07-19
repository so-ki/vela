export const syntheticMeta = Object.freeze({
  simulated: true as const,
  evidence_origin: 'synthetic_demo' as const,
  status: 'demo_only' as const,
  formal_release_allowed: false as const,
})

export type SyntheticMeta = typeof syntheticMeta
export type SyntheticRecord<T extends object> = T & SyntheticMeta

const demo = <T extends object>(record: T): SyntheticRecord<T> => ({
  ...record,
  ...syntheticMeta,
})

export const rc0SyntheticCase = demo({
  id: 'SYN-RC0-20260719-001',
  title: 'Projeto Aurora · 储能系统绿地投资协查',
  company: 'Aurora Grid Systems（虚构）',
  summary: '拟在巴西圣保罗州建设储能系统集成与测试设施。本对象只用于展示工程工作流，不代表真实客户、律师意见或生产事实。',
  context: {
    country: '巴西 / Brazil',
    state: '圣保罗州 / São Paulo',
    industry: '新能源 · 储能系统集成',
    actionType: '绿地投资 / Greenfield',
  },
  versions: {
    pack: 'brazil_new_energy_greenfield@1.3.1',
    rules: '2.9',
    corpus: '1.13',
    compiler: '0.2',
    coverageProof: '0.1',
    snapshot: '1.0',
    release: '1.1',
  },
  currentStage: 'CoverageProof 工程重验完成；外部认证未开始',
  gate: 'blocked_external',
  contentState: 'engineering_demonstrator_rc0',
  externalBlocks: [
    '两名真实巴西执业律师内容认证',
    '真实客户 UAT 与具名签署',
    '客户生产部署、SBOM、provenance 与 runtime probe',
  ],
  nextAction: '由具名外部责任方提供真实证据；工程团队不得用拟制对象代替。',
  metrics: [
    demo({ label: '材料', value: '6', detail: '4 已抽取 · 2 待补充', tone: 'progress' }),
    demo({ label: '冻结调查分母', value: '30', detail: '本次 scope 18', tone: 'neutral' }),
    demo({ label: '已支持 Claim', value: '7', detail: '均为拟制演示状态', tone: 'demo' }),
    demo({ label: '外部阻断', value: '3', detail: 'formal release 不允许', tone: 'blocked' }),
  ],
  materials: [
    demo({ id: 'MAT-001', name: '项目投资说明（拟制）.pdf', kind: '项目说明', extraction: 'extracted', ledger: 'confirmed', source: '业务上传 · 拟制', owner: '业务负责人', missing: '无' }),
    demo({ id: 'MAT-002', name: '选址参数表（拟制）.xlsx', kind: '场址数据', extraction: 'extracted', ledger: 'confirmed', source: '项目团队 · 拟制', owner: '工程经理', missing: '地块权属链' }),
    demo({ id: 'MAT-003', name: '工艺与设备清单（拟制）.docx', kind: '工艺材料', extraction: 'review', ledger: 'needs_review', source: '技术团队 · 拟制', owner: '技术负责人', missing: '危险品最大库存' }),
    demo({ id: 'MAT-004', name: '用工计划（拟制）.pdf', kind: '人力计划', extraction: 'extracted', ledger: 'confirmed', source: '人力团队 · 拟制', owner: 'HR', missing: '外籍人员岗位拆分' }),
  ],
  facts: [
    demo({ id: 'FACT-001', subject: 'Aurora 项目', attribute: '计划投资', value: 'R$ 180,000,000（拟制）', time: '2027–2029', source: 'MAT-001 §2.1', confirmation: 'business_confirmed' }),
    demo({ id: 'FACT-002', subject: 'Aurora 项目', attribute: '场址面积', value: '42,000 m²（拟制）', time: '2026-07-01', source: 'MAT-002!B12', confirmation: 'business_confirmed' }),
    demo({ id: 'FACT-003', subject: '生产设施', attribute: '电池电芯制造', value: '不涉及；仅系统集成（拟制）', time: '规划期', source: 'MAT-003 §1.4', confirmation: 'needs_review' }),
    demo({ id: 'FACT-004', subject: '人员计划', attribute: '预计雇员', value: '160 人（拟制）', time: '投产年', source: 'MAT-004 p.3', confirmation: 'business_confirmed' }),
  ],
  checklist: [
    demo({ code: 'ENV-001', group: '环境与许可', title: '确认州级环境许可路径与主管机关', priority: 'P0', state: 'supported_demo', missing: '最终场址坐标', owner: '法务研究', next: '补齐坐标后重验适用路径' }),
    demo({ code: 'IND-003', group: '行业准入', title: '核验储能系统集成活动的登记与技术责任', priority: 'P0', state: 'pending_review', missing: '设备技术分类', owner: '技术 + 法务', next: '确认 NCM/活动代码' }),
    demo({ code: 'LAB-002', group: '劳动用工', title: '建立本地雇佣、职业安全与培训责任表', priority: 'P1', state: 'supported_demo', missing: '岗位风险清单', owner: 'HR + 法务', next: '补充分岗位危险源' }),
    demo({ code: 'TAX-004', group: '税务与激励', title: '核验州/市激励的资格与持续义务', priority: 'P1', state: 'unanswerable', missing: '具体市镇与激励方案', owner: '税务顾问', next: '选择候选市镇后重新研究' }),
    demo({ code: 'DATA-001', group: '数据合规', title: '梳理员工与供应商个人数据处理活动', priority: 'P1', state: 'uncovered', missing: '系统与跨境传输清单', owner: '隐私负责人', next: '建立 data inventory' }),
  ],
  researchItems: [
    demo({
      code: 'ENV-001', title: '州级环境许可路径', rule: '按活动、规模与潜在影响核验许可机关及分阶段许可要求；当前仅作拟制结构演示。',
      elements: ['活动技术分类', '场址坐标', '潜在影响等级'], mappedFacts: ['FACT-002', 'FACT-003'], exceptions: '最终分类可能改变主管机关与文件组合。', limitations: '没有真实场址、专家意见或时点核验。',
      evidence: [
        demo({ authority: 'Estado de São Paulo（演示标签）', jurisdiction: 'São Paulo / BR', effectiveDate: '未作真实时点核验', pinpoint: '拟制定位 ENV-DEMO-01', sourceType: 'official_source_placeholder', reviewStatus: 'demo_only', contentHash: 'sha256:demo-env-001-not-evidence', version: 'synthetic@1', relation: '用于展示 Claim 的 source-backed 结构，不证明适用。' }),
        demo({ authority: 'Federal framework（演示标签）', jurisdiction: 'Brazil', effectiveDate: '未作真实时点核验', pinpoint: '拟制定位 ENV-DEMO-02', sourceType: 'official_source_placeholder', reviewStatus: 'demo_only', contentHash: 'sha256:demo-env-002-not-evidence', version: 'synthetic@1', relation: '仅展示上位框架与州级路径的关联。' }),
      ],
    }),
    demo({
      code: 'IND-003', title: '技术责任与活动登记', rule: '先冻结实际活动与设备分类，再映射登记、技术责任和持续义务。',
      elements: ['实际经营活动', '设备分类', '责任专业'], mappedFacts: ['FACT-003'], exceptions: '进口、制造与系统集成的义务可能不同。', limitations: '设备分类尚缺，禁止给出确定结论。',
      evidence: [
        demo({ authority: 'Competent authority（拟制）', jurisdiction: 'Brazil', effectiveDate: 'unknown', pinpoint: 'IND-DEMO-01', sourceType: 'research_placeholder', reviewStatus: 'needs_review', contentHash: 'sha256:demo-ind-001-not-evidence', version: 'synthetic@1', relation: '对应缺失设备分类，当前 Claim 只能 pending。' }),
      ],
    }),
    demo({
      code: 'LAB-002', title: '职业安全与培训责任', rule: '按岗位危险源、设备操作和雇佣结构建立责任矩阵。',
      elements: ['岗位清单', '危险源', '培训与记录'], mappedFacts: ['FACT-004'], exceptions: '承包商与直接雇员责任边界需分别核验。', limitations: '岗位风险清单未提交。',
      evidence: [
        demo({ authority: 'Labor authority（拟制）', jurisdiction: 'Brazil', effectiveDate: 'unknown', pinpoint: 'LAB-DEMO-01', sourceType: 'research_placeholder', reviewStatus: 'demo_only', contentHash: 'sha256:demo-lab-001-not-evidence', version: 'synthetic@1', relation: '展示培训义务与事实字段的绑定方式。' }),
      ],
    }),
  ],
  claims: [
    demo({ code: 'ENV-001', statement: '在冻结场址和活动分类前，不得确定最终许可路径。', factRefs: ['FACT-002', 'FACT-003'], evidenceRefs: ['ENV-DEMO-01', 'ENV-DEMO-02'], reasonCodes: ['missing_final_site_coordinates'], humanDecision: 'confirmed_demo_only', unanswerable: '无', missingFacts: ['最终坐标'], next: '业务补充坐标；法务重验' }),
    demo({ code: 'IND-003', statement: '技术登记责任取决于尚未确认的设备与活动分类。', factRefs: ['FACT-003'], evidenceRefs: ['IND-DEMO-01'], reasonCodes: ['equipment_classification_missing'], humanDecision: 'awaiting_human_confirmation', unanswerable: '设备分类缺失', missingFacts: ['NCM/活动代码'], next: '技术团队确认分类' }),
    demo({ code: 'TAX-004', statement: '未选择具体市镇，无法判断地方激励资格。', factRefs: [], evidenceRefs: [], reasonCodes: ['municipality_not_selected', 'zero_authoritative_hit'], humanDecision: 'refused_demo_only', unanswerable: '缺少法域与权威来源', missingFacts: ['候选市镇', '激励方案'], next: '缩小范围后重新检索' }),
  ],
  coverage: demo({
    denominatorRef: 'pack:brazil_new_energy_greenfield@1.3.1#synthetic-scope',
    denominatorHash: 'sha256:synthetic-denominator-not-evidence',
    proofHash: 'sha256:synthetic-proof-not-evidence',
    generatedAt: '2026-07-19T09:45:00+08:00',
    compilerVersion: '0.2', schemaVersion: '0.1',
    counts: { supported: 7, pending: 5, refused: 2, unanswerable: 3, uncovered: 1, outOfScope: 12, total: 30, scopeTotal: 18 },
  }),
  deliveryStages: [
    demo({ name: 'Compiler', state: 'demo', detail: '0.2 · synthetic snapshot', hash: '5e566256…ded0b' }),
    demo({ name: 'Claim Confirmation', state: 'demo', detail: '7 项拟制确认', hash: 'human-demo-only' }),
    demo({ name: 'CoverageProof', state: 'demo', detail: '0.1 · scope 18/30', hash: '206cb553…807ffb' }),
    demo({ name: 'Answerability Gate', state: 'demo', detail: '仅工程演示通过', hash: 'e40f6805…6f257a' }),
    demo({ name: 'Snapshot', state: 'demo', detail: '1.0 · 不可正式签署', hash: 'e3dfe751…01f88' }),
    demo({ name: 'Expert Attestation', state: 'blocked', detail: 'blocked_external · 无真实律师签署', hash: 'missing' }),
    demo({ name: 'UAT', state: 'blocked', detail: 'blocked_external · 无真实客户验收', hash: 'missing' }),
    demo({ name: 'Deployment Evidence', state: 'blocked', detail: 'blocked_external · 无客户生产证据', hash: 'missing' }),
    demo({ name: 'Release', state: 'blocked', detail: 'formal_release_allowed=false', hash: 'not-created' }),
  ],
  audit: [
    demo({ at: '2026-07-19 09:32 CST', actor: 'RC0 engineering runner', action: '创建拟制演示对象', version: 'synthetic@1', hash: 'demo-object', change: 'not_started → demo_only', result: 'demo_only', reason: '与正式证据库隔离' }),
    demo({ at: '2026-07-19 09:44 CST', actor: 'Versioned evaluator', action: '重验冻结 reader', version: '0.2 / 0.1 / 1.0 / 1.1', hash: 'goldens unchanged', change: 'engineering check', result: 'verified_engineering', reason: '不外推法律正确性' }),
    demo({ at: '2026-07-19 09:46 CST', actor: 'Formal Release Gate', action: '检查外部证据', version: 'release 1.1', hash: 'no release hash', change: 'blocked_external → blocked_external', result: 'blocked', reason: '真实律师、UAT、部署证据均缺失' }),
  ],
})

export const syntheticRecordGroups = [
  rc0SyntheticCase.metrics,
  rc0SyntheticCase.materials,
  rc0SyntheticCase.facts,
  rc0SyntheticCase.checklist,
  rc0SyntheticCase.researchItems,
  rc0SyntheticCase.researchItems.flatMap((item) => item.evidence),
  rc0SyntheticCase.claims,
  [rc0SyntheticCase.coverage],
  rc0SyntheticCase.deliveryStages,
  rc0SyntheticCase.audit,
]
