<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  decideExpertSignature,
  decideLegalCredential,
  downloadCandidateArtifact,
  fetchDeliveryArtifactManifest,
  fetchDeliveryArtifacts,
  fetchDeliveryGateStatus,
  fetchDeliveryReleases,
  fetchDeploymentEvidence,
  fetchExpertAttestations,
  fetchLegalContentCertifications,
  fetchLegalCredentials,
  fetchScenario,
  fetchUATAcceptances,
  freezeDeliveryArtifacts,
  previewLegalContentManifest,
  revokeDeliveryRelease,
  revokeDeploymentEvidence,
  revokeExpertAttestation,
  revokeLegalContentCertification,
  submitDeliveryRelease,
  submitDeploymentEvidence,
  submitExpertAttestation,
  submitLegalContentCertification,
  submitLegalCredential,
  submitUATAcceptance,
  withdrawUATAcceptance,
} from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  ArtifactManifest,
  DeliveryArtifact,
  DeliveryRelease,
  DeploymentEvidence,
  ExpertAttestation,
  LegalContentCertification,
  LegalCredential,
  UATAcceptance,
} from '@/types/delivery'
import type { DeliveryGateStatus } from '@/types/mechanism'
import type { Scenario } from '@/types/scenario'

const route = useRoute()
const auth = useAuthStore()
const scenarioId = computed(() => Number(route.params.id))
const isAdmin = computed(() => auth.user?.role === 'admin')
const isExactLegal = computed(() => auth.user?.role === 'legal')
const isBusiness = computed(() => auth.user?.role === 'business')

const scenario = ref<Scenario | null>(null)
const gate = ref<DeliveryGateStatus | null>(null)
const artifacts = ref<DeliveryArtifact[]>([])
const manifest = ref<ArtifactManifest | null>(null)
const credentials = ref<LegalCredential[]>([])
const attestations = ref<ExpertAttestation[]>([])
const acceptances = ref<UATAcceptance[]>([])
const certifications = ref<LegalContentCertification[]>([])
const deployments = ref<DeploymentEvidence[]>([])
const releases = ref<DeliveryRelease[]>([])
const loading = ref(true)
const busy = ref<string | null>(null)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const contentManifestPreview = ref<{ manifest: Record<string, unknown>; manifest_hash: string } | null>(null)
const deliveryArtifactCount = computed(() => {
  if (manifest.value) return manifest.value.artifact_manifest.length
  const latestSnapshot = artifacts.value[0]?.snapshot_hash
  return latestSnapshot
    ? artifacts.value.filter(
        (item) => item.snapshot_hash === latestSnapshot && item.status === 'released',
      ).length
    : 0
})

const forms = reactive({
  credential: '',
  credentialDecisionId: '',
  credentialDecision: '',
  attestation: '',
  uat: '',
  contentManifest: '',
  contentCertification: '',
  deployment: '',
  release: '',
  revokeKind: '',
  revokeId: '',
  revokeReason: '',
})

// Deliberately invalid placeholders: the API must reject a template until the
// operator replaces every external assertion with a real evidence value.
const requiredHash = 'REPLACE_WITH_64_HEX_SHA256'

function futureIso(days: number) {
  return new Date(Date.now() + days * 86_400_000).toISOString()
}

function pretty(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}

function currentSnapshot() {
  return scenario.value?.scenario_scope?.snapshot
}

function active<T extends { status: string }>(values: T[], status: string) {
  return values.find((item) => item.status === status)
}

function refreshTemplates() {
  const snapshot = currentSnapshot()
  const verified = credentials.value.filter((item) => item.status === 'verified')
  const ownCredential = credentials.value.find((item) => item.user_id === auth.user?.id)
  const candidateIds = artifacts.value
    .filter((item) => item.status === 'candidate')
    .map((item) => item.id)

  if (!forms.credential) {
    forms.credential = pretty({
      holder_name: auth.user?.full_name || '',
      jurisdiction: 'BR',
      authority: 'OAB/SP',
      registration_number: '',
      official_register_url: 'https://consulta.oab.org.br/',
      submitted_evidence_hash: requiredHash,
    })
  }
  if (!forms.credentialDecision) {
    forms.credentialDecision = pretty({
      decision: 'verified',
      expected_revision: 0,
      note: 'OAB CNA and ConfirmADV official evidence independently reviewed.',
      verification_reference: 'https://confirmadv.oab.org.br/',
      verification_evidence_hash: requiredHash,
      registration_status: 'regular',
      valid_until: futureIso(60),
    })
  }
  if (!forms.attestation) {
    forms.attestation = pretty({
      credential_id: ownCredential?.id || '',
      artifact_ids: candidateIds,
      signed_artifact_manifest_hash: manifest.value?.artifact_manifest_hash || requiredHash,
      signature_format: 'PAdES',
      signature_artifact_hash: requiredHash,
      signature_validation_url: 'https://validar.iti.gov.br/',
      signature_validation_report_hash: requiredHash,
      certificate_subject: `CN=${auth.user?.full_name || ''}`,
      certificate_serial: '',
      certificate_valid_until: futureIso(45),
      statement:
        'I reviewed the frozen facts, legal sources, claims, limitations and exact artifact hashes for this scope.',
      limitations: 'Approval is limited to the frozen scope, sources and legal date recorded in the manifest.',
      expires_at: futureIso(30),
    })
  }
  if (!forms.uat) {
    forms.uat = pretty({
      expert_attestation_id: active(attestations.value, 'active')?.id || '',
      customer_organization: auth.user?.organization || '',
      test_plan_hash: requiredHash,
      test_evidence_hash: requiredHash,
      evidence_reference: 'REPLACE_WITH_HTTPS_UAT_EVIDENCE_URL',
      environment: 'customer_acceptance',
      target_environment_id: '',
      acceptance_statement:
        'The customer owner accepts this exact frozen delivery set for the controlled scope and recorded limitations.',
      expires_at: futureIso(20),
    })
  }
  if (!forms.contentManifest) {
    forms.contentManifest = pretty({
      capability_pack_id: snapshot?.capability_pack_id || '',
      capability_pack_version: snapshot?.capability_pack_version || '',
      capability_pack_hash: snapshot?.capability_pack_hash || requiredHash,
      rules_artifact_hash: snapshot?.rules_artifact_hash || requiredHash,
      corpus_artifact_hash: snapshot?.corpus_artifact_hash || requiredHash,
      gold_dataset_sha256: requiredHash,
      evaluation_policy_sha256: requiredHash,
      evaluation_run_sha256: requiredHash,
      regression_status: 'passed',
      primary_credential_id: verified[0]?.id || '',
      secondary_credential_id: verified[1]?.id || '',
      limitations: 'Certification is limited to the frozen release and declared legal date.',
    })
  }
  if (!forms.deployment) {
    forms.deployment = pretty({
      legal_content_certification_id: active(certifications.value, 'certified')?.id || '',
      environment: 'production',
      target_environment_id: '',
      commit_sha: 'REPLACE_WITH_40_OR_64_HEX_GIT_COMMIT',
      migration_head: '20260718_0005',
      ci_run_url: 'REPLACE_WITH_GITHUB_ACTIONS_RUN_URL',
      artifact_sha256: requiredHash,
      sbom_sha256: requiredHash,
      security_evidence_url: 'REPLACE_WITH_HTTPS_SECURITY_EVIDENCE_URL',
      provenance_url: 'REPLACE_WITH_HTTPS_PROVENANCE_URL',
      provenance_sha256: requiredHash,
      runtime_probe_url: 'REPLACE_WITH_HTTPS_RUNTIME_PROBE_URL',
      runtime_probe_sha256: requiredHash,
      backend_image_digest: `sha256:${requiredHash}`,
      frontend_image_digest: `sha256:${requiredHash}`,
      database_image_digest: `sha256:${requiredHash}`,
      config_schema_sha256: requiredHash,
      capability_pack_hash: snapshot?.capability_pack_hash || requiredHash,
      rules_artifact_hash: snapshot?.rules_artifact_hash || requiredHash,
      corpus_artifact_hash: snapshot?.corpus_artifact_hash || requiredHash,
      gold_dataset_sha256: requiredHash,
      evaluation_policy_sha256: requiredHash,
      evaluation_run_sha256: requiredHash,
      regression_status: 'passed',
      verification_note:
        'Production images, migration, probes, provenance, SBOM, security policy and gold run independently reviewed.',
      expires_at: futureIso(15),
    })
  }
  if (!forms.release) {
    forms.release = pretty({
      expert_attestation_id: active(attestations.value, 'active')?.id || '',
      uat_acceptance_id: active(acceptances.value, 'accepted')?.id || '',
      deployment_evidence_id: active(deployments.value, 'verified')?.id || '',
      release_note: 'All independently supplied evidence is present, current and bound to this exact snapshot.',
      expires_at: futureIso(10),
    })
  }
}

async function optional<T>(work: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await work()
  } catch {
    return fallback
  }
}

async function loadPage() {
  loading.value = true
  error.value = null
  try {
    const [loadedScenario, loadedGate, loadedArtifacts, loadedManifest, loadedAttestations, loadedUat, loadedReleases] =
      await Promise.all([
        fetchScenario(scenarioId.value),
        fetchDeliveryGateStatus(scenarioId.value),
        fetchDeliveryArtifacts(scenarioId.value),
        optional(() => fetchDeliveryArtifactManifest(scenarioId.value), null),
        fetchExpertAttestations(scenarioId.value),
        fetchUATAcceptances(scenarioId.value),
        fetchDeliveryReleases(scenarioId.value),
      ])
    scenario.value = loadedScenario
    gate.value = loadedGate
    artifacts.value = loadedArtifacts
    manifest.value = loadedManifest
    attestations.value = loadedAttestations
    acceptances.value = loadedUat
    releases.value = loadedReleases

    if (isExactLegal.value || isAdmin.value) {
      credentials.value = await fetchLegalCredentials()
      certifications.value = await fetchLegalContentCertifications()
    }
    if (isAdmin.value) deployments.value = await fetchDeploymentEvidence()
    refreshTemplates()
  } catch (cause: unknown) {
    error.value = extractError(cause, '无法加载客户交付证据台')
  } finally {
    loading.value = false
  }
}

onMounted(loadPage)

async function runJsonAction(
  key: string,
  raw: string,
  action: (payload: Record<string, unknown>) => Promise<unknown>,
  success: string,
) {
  busy.value = key
  error.value = null
  notice.value = null
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>
    await action(payload)
    notice.value = success
    await loadPage()
  } catch (cause: unknown) {
    error.value = extractError(cause, '提交失败；请核对 JSON、角色和证据链')
  } finally {
    busy.value = null
  }
}

async function freezeArtifacts() {
  busy.value = 'freeze'
  error.value = null
  try {
    await freezeDeliveryArtifacts(scenarioId.value)
    notice.value = '三个候选制品已按当前快照冻结；它们尚未获客户交付授权。'
    forms.attestation = ''
    await loadPage()
  } catch (cause: unknown) {
    error.value = extractError(cause, '冻结失败；请先完成 Answerability Gate')
  } finally {
    busy.value = null
  }
}

async function downloadCandidate(artifact: DeliveryArtifact) {
  busy.value = `download-${artifact.id}`
  try {
    const { blob, filename } = await downloadCandidateArtifact(scenarioId.value, artifact.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (cause: unknown) {
    error.value = extractError(cause, '候选件下载失败')
  } finally {
    busy.value = null
  }
}

async function previewContentManifest() {
  busy.value = 'content-manifest'
  error.value = null
  try {
    const payload = JSON.parse(forms.contentManifest) as Record<string, unknown>
    contentManifestPreview.value = await previewLegalContentManifest(payload)
    forms.contentCertification = pretty({
      ...payload,
      primary_signature_hash: requiredHash,
      primary_certificate_subject: '',
      primary_certificate_serial: '',
      primary_validation_url: 'https://validar.iti.gov.br/',
      primary_validation_report_hash: requiredHash,
      secondary_signature_hash: requiredHash,
      secondary_certificate_subject: '',
      secondary_certificate_serial: '',
      secondary_validation_url: 'https://validar.iti.gov.br/',
      secondary_validation_report_hash: requiredHash,
      signed_content_manifest_hash: contentManifestPreview.value.manifest_hash,
      expires_at: futureIso(20),
    })
    notice.value = 'canonical content manifest 已生成；请让两名律师对显示的 hash 完成外部签名。'
  } catch (cause: unknown) {
    error.value = extractError(cause, 'manifest 生成失败')
  } finally {
    busy.value = null
  }
}

async function decideSignature(item: ExpertAttestation, decision: 'approved' | 'rejected') {
  busy.value = `signature-${item.id}`
  error.value = null
  try {
    await decideExpertSignature(scenarioId.value, item.id, {
      decision,
      note:
        decision === 'approved'
          ? 'ITI VALIDAR report, certificate subject and exact artifact manifest hash independently checked.'
          : 'Independent signature verification failed; the submitted evidence must not be released.',
    })
    notice.value = decision === 'approved' ? '签名核验通过。' : '签名已拒绝。'
    forms.uat = ''
    await loadPage()
  } catch (cause: unknown) {
    error.value = extractError(cause, '签名决定失败')
  } finally {
    busy.value = null
  }
}

async function submitRevocation() {
  const reason = forms.revokeReason.trim()
  if (!forms.revokeKind || !forms.revokeId.trim() || reason.length < 10) {
    error.value = '撤回必须选择对象类型、填写对象 ID，并提供至少 10 个字符的真实原因。'
    return
  }
  busy.value = 'revoke'
  error.value = null
  try {
    if (forms.revokeKind === 'attestation') {
      await revokeExpertAttestation(scenarioId.value, forms.revokeId.trim(), reason)
    } else if (forms.revokeKind === 'uat') {
      await withdrawUATAcceptance(scenarioId.value, forms.revokeId.trim(), reason)
    } else if (forms.revokeKind === 'content-certification') {
      await revokeLegalContentCertification(forms.revokeId.trim(), reason)
    } else if (forms.revokeKind === 'deployment') {
      await revokeDeploymentEvidence(forms.revokeId.trim(), reason)
    } else if (forms.revokeKind === 'release') {
      await revokeDeliveryRelease(scenarioId.value, forms.revokeId.trim(), reason)
    } else {
      throw new Error('unsupported revocation kind')
    }
    forms.revokeId = ''
    forms.revokeReason = ''
    notice.value = '撤回已记录；交付门状态已重新计算。'
    await loadPage()
  } catch (cause: unknown) {
    error.value = extractError(cause, '撤回失败；请确认角色、对象状态与 ID')
  } finally {
    busy.value = null
  }
}

function shortHash(value?: string | null) {
  return value ? `${value.slice(0, 12)}…${value.slice(-8)}` : '—'
}

function extractError(cause: unknown, fallback: string) {
  if (typeof cause === 'object' && cause !== null && 'response' in cause) {
    const response = (cause as { response?: { data?: { detail?: unknown } } }).response
    const detail = response?.data?.detail
    if (typeof detail === 'string') return detail
    if (detail) return JSON.stringify(detail, null, 2)
  }
  if (cause instanceof SyntaxError) return 'JSON 格式无效：' + cause.message
  return fallback
}
</script>

<template>
  <div class="delivery-page page-stack">
    <header class="page-header delivery-header">
      <div>
        <RouterLink :to="`/scenarios/${scenarioId}/mechanism`" class="back-link">← 保证机制工作台</RouterLink>
        <h1>客户交付证据台</h1>
        <p class="muted">{{ scenario?.project_name }} · 场景 {{ scenarioId }}</p>
      </div>
      <button type="button" class="btn-secondary" :disabled="loading" @click="loadPage">重新核验</button>
    </header>

    <p v-if="error" class="banner banner-error"><strong>阻断：</strong>{{ error }}</p>
    <p v-if="notice" class="banner banner-success">{{ notice }}</p>

    <section class="gate-card" :class="gate?.delivery_allowed ? 'allowed' : 'blocked'">
      <div>
        <span class="eyebrow">实时 fail-closed 判定</span>
        <h2>{{ gate?.delivery_allowed ? '已获限时客户交付许可' : '当前禁止客户交付' }}</h2>
      </div>
      <div class="gate-meta">
        <span>snapshot {{ shortHash(gate?.snapshot_hash) }}</span>
        <span>release {{ shortHash(gate?.release_hash) }}</span>
      </div>
      <ul v-if="gate?.blocking_reasons.length" class="reason-list">
        <li v-for="reason in gate.blocking_reasons" :key="reason">{{ reason }}</li>
      </ul>
      <p class="boundary">{{ gate?.boundary }}</p>
    </section>

    <div v-if="loading" class="panel muted">正在重算证据链…</div>

    <template v-else>
      <section class="evidence-grid" aria-label="交付证据链进度">
        <article><b>{{ isBusiness ? '—' : credentials.filter((v) => v.status === 'verified').length }}</b><span>有效 OAB 凭证{{ isBusiness ? '（受限）' : '' }}</span></article>
        <article><b>{{ isBusiness ? '—' : certifications.filter((v) => v.status === 'certified').length }}</b><span>双律师内容认证{{ isBusiness ? '（受限）' : '' }}</span></article>
        <article><b>{{ deliveryArtifactCount }}/3</b><span>精确冻结制品</span></article>
        <article><b>{{ attestations.filter((v) => v.status === 'active').length }}</b><span>已核验场景签名</span></article>
        <article><b>{{ acceptances.filter((v) => v.status === 'accepted').length }}</b><span>客户 UAT</span></article>
        <article><b>{{ releases.filter((v) => v.status === 'active').length }}</b><span>有效 release</span></article>
      </section>

      <section class="panel evidence-section">
        <div class="section-heading">
          <div><span class="step">01</span><h2>冻结并审阅精确候选件</h2></div>
          <button v-if="isExactLegal" type="button" class="btn-primary" :disabled="!!busy" @click="freezeArtifacts">
            冻结当前 DOCX / PDF / audit
          </button>
        </div>
        <p class="muted">候选下载仅用于律师签署和客户 UAT，响应明确未获客户交付授权。重新冻结会 supersede 旧候选批次。</p>
        <div v-if="manifest" class="hash-box">
          <span>canonical artifact manifest hash</span>
          <code>{{ manifest.artifact_manifest_hash }}</code>
        </div>
        <div class="artifact-list">
          <article v-for="item in artifacts" :key="item.id" class="artifact-row">
            <div><b>{{ item.artifact_type.toUpperCase() }}</b><span class="status" :data-status="item.status">{{ item.status }}</span></div>
            <code>{{ shortHash(item.content_sha256) }}</code>
            <span>{{ item.content_length.toLocaleString() }} bytes</span>
            <button v-if="item.status === 'candidate'" type="button" class="btn-secondary sm" :disabled="!!busy" @click="downloadCandidate(item)">审阅候选 bytes</button>
          </article>
        </div>
      </section>

      <section v-if="isExactLegal || isAdmin" class="panel evidence-section">
        <div class="section-heading"><div><span class="step">02</span><h2>律师身份与 OAB 独立核验</h2></div></div>
        <div class="record-list">
          <div v-for="item in credentials" :key="item.id" class="record-row">
            <div><b>{{ item.holder_name }}</b><small>{{ item.authority }} · {{ item.registration_number }}</small></div>
            <span class="status" :data-status="item.status">{{ item.status }}</span>
            <code>{{ item.id }}</code>
          </div>
        </div>
        <details v-if="isExactLegal" class="action-panel">
          <summary>提交本人执业凭证</summary>
          <textarea v-model="forms.credential" rows="11" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy" @click="runJsonAction('credential', forms.credential, submitLegalCredential, '凭证已提交，等待独立管理员核验。')">提交凭证</button>
        </details>
        <details v-if="isAdmin" class="action-panel">
          <summary>核验 / 拒绝 / 撤回凭证</summary>
          <label>credential ID<input v-model="forms.credentialDecisionId" /></label>
          <textarea v-model="forms.credentialDecision" rows="10" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy || !forms.credentialDecisionId" @click="runJsonAction('credential-decision', forms.credentialDecision, (payload) => decideLegalCredential(forms.credentialDecisionId, payload), '凭证决定已记录。')">提交独立核验决定</button>
        </details>
      </section>

      <section class="panel evidence-section">
        <div class="section-heading"><div><span class="step">03</span><h2>场景律师签署与独立验证</h2></div></div>
        <div class="record-list">
          <div v-for="item in attestations" :key="item.id" class="record-row">
            <div><b>{{ item.signature_format }}</b><small>manifest {{ shortHash(item.artifact_manifest_hash) }}</small></div>
            <span class="status" :data-status="item.status">{{ item.status }}</span>
            <code>{{ item.id }}</code>
            <div v-if="isAdmin && item.status === 'pending_validation'" class="inline-actions">
              <button type="button" class="btn-primary sm" :disabled="!!busy" @click="decideSignature(item, 'approved')">批准 VALIDAR 核验</button>
              <button type="button" class="btn-secondary sm" :disabled="!!busy" @click="decideSignature(item, 'rejected')">拒绝</button>
            </div>
          </div>
        </div>
        <details v-if="isExactLegal" class="action-panel">
          <summary>提交外部数字签名证据</summary>
          <p class="muted">先下载并检查三个候选件，对上方 canonical manifest hash 外部签名，再提交 VALIDAR 报告与证书身份。</p>
          <textarea v-model="forms.attestation" rows="20" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy" @click="runJsonAction('attestation', forms.attestation, (payload) => submitExpertAttestation(scenarioId, payload), '签名证据已提交，等待独立管理员核验。')">提交签名证据</button>
        </details>
      </section>

      <section class="panel evidence-section">
        <div class="section-heading"><div><span class="step">04</span><h2>客户 UAT</h2></div></div>
        <div class="record-list">
          <div v-for="item in acceptances" :key="item.id" class="record-row">
            <div><b>{{ item.customer_organization }}</b><small>{{ item.target_environment_id }}</small></div>
            <span class="status" :data-status="item.status">{{ item.status }}</span>
            <code>{{ item.id }}</code>
          </div>
        </div>
        <details v-if="isBusiness" class="action-panel">
          <summary>由场景提交人签署 UAT</summary>
          <textarea v-model="forms.uat" rows="13" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy" @click="runJsonAction('uat', forms.uat, (payload) => submitUATAcceptance(scenarioId, payload), '客户 UAT 已绑定到冻结快照和目标环境。')">提交 UAT</button>
        </details>
      </section>

      <section v-if="isAdmin" class="panel evidence-section admin-zone">
        <div class="section-heading"><div><span class="step">05</span><h2>双律师内容认证与生产证据</h2></div></div>
        <p class="warning-note">这里记录外部真实证据，不会生成或伪造 OAB、ITI、gold、CI、SBOM、provenance 或 runtime probe。</p>
        <details class="action-panel">
          <summary>A. 生成双签 canonical content manifest</summary>
          <textarea v-model="forms.contentManifest" rows="16" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy" @click="previewContentManifest">生成待签 hash</button>
          <div v-if="contentManifestPreview" class="hash-box"><span>待两名律师签署</span><code>{{ contentManifestPreview.manifest_hash }}</code></div>
        </details>
        <details class="action-panel">
          <summary>B. 记录双签与 ITI VALIDAR 报告</summary>
          <textarea v-model="forms.contentCertification" rows="24" spellcheck="false" placeholder="先完成 A，系统会生成认证提交模板" />
          <button type="button" class="btn-primary" :disabled="!!busy || !forms.contentCertification" @click="runJsonAction('content-certification', forms.contentCertification, submitLegalContentCertification, '双律师内容认证已记录。')">提交内容认证</button>
        </details>
        <div class="record-list">
          <div v-for="item in certifications" :key="item.id" class="record-row"><div><b>{{ item.capability_pack_id }} {{ item.capability_pack_version }}</b><small>{{ shortHash(item.certification_manifest_hash) }}</small></div><span class="status" :data-status="item.status">{{ item.status }}</span><code>{{ item.id }}</code></div>
        </div>
        <details class="action-panel">
          <summary>C. 记录 production provenance / SBOM / gold / runtime probe</summary>
          <textarea v-model="forms.deployment" rows="30" spellcheck="false" />
          <button type="button" class="btn-primary" :disabled="!!busy" @click="runJsonAction('deployment', forms.deployment, submitDeploymentEvidence, '生产部署证据已记录。')">提交部署证据</button>
        </details>
        <div class="record-list">
          <div v-for="item in deployments" :key="item.id" class="record-row"><div><b>{{ item.environment }} · {{ item.target_environment_id }}</b><small>{{ item.migration_head }} · {{ shortHash(item.commit_sha) }}</small></div><span class="status" :data-status="item.status">{{ item.status }}</span><code>{{ item.id }}</code></div>
        </div>
      </section>

      <section v-if="isAdmin" class="panel evidence-section release-zone">
        <div class="section-heading"><div><span class="step">06</span><h2>创建限时客户交付 release</h2></div></div>
        <textarea v-model="forms.release" rows="9" spellcheck="false" />
        <button type="button" class="btn-primary" :disabled="!!busy" @click="runJsonAction('release', forms.release, (payload) => submitDeliveryRelease(scenarioId, payload), 'release 已创建；系统将立即重算全部依赖。')">重算并创建 release</button>
      </section>

      <section class="panel evidence-section">
        <div class="section-heading"><div><span class="step">07</span><h2>发布记录</h2></div></div>
        <div class="record-list">
          <div v-for="item in releases" :key="item.id" class="record-row"><div><b>release {{ shortHash(item.release_hash) }}</b><small>有效至 {{ new Date(item.expires_at).toLocaleString() }}</small></div><span class="status" :data-status="item.status">{{ item.status }}</span><code>{{ item.id }}</code></div>
        </div>
        <p v-if="!releases.length" class="muted">尚无 release。最终 Word/PDF/audit 下载仍会返回 409。</p>
      </section>

      <section class="panel evidence-section revoke-zone">
        <div class="section-heading"><div><span class="step">08</span><h2>撤回与紧急阻断</h2></div></div>
        <p class="muted">撤回立即影响实时门禁。只有原签署人、原 UAT 提交人或 admin 能撤回其权限范围内的对象。</p>
        <div class="revoke-form">
          <label>对象类型
            <select v-model="forms.revokeKind">
              <option value="">请选择</option>
              <option v-if="isExactLegal || isAdmin" value="attestation">场景律师签署</option>
              <option v-if="isBusiness" value="uat">客户 UAT</option>
              <option v-if="isAdmin" value="content-certification">双律师内容认证</option>
              <option v-if="isAdmin" value="deployment">部署证据</option>
              <option v-if="isAdmin" value="release">客户交付 release</option>
            </select>
          </label>
          <label>对象 ID<input v-model="forms.revokeId" /></label>
          <label>真实撤回原因<input v-model="forms.revokeReason" /></label>
          <button type="button" class="btn-secondary" :disabled="!!busy" @click="submitRevocation">确认撤回并重算</button>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.delivery-page { max-width: 1240px; margin: 0 auto; }
.delivery-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; }
.delivery-header h1 { margin: .35rem 0 .2rem; }
.banner { padding: .9rem 1rem; border-radius: 12px; white-space: pre-wrap; }
.banner-error { background: #fff0f0; color: #991b1b; border: 1px solid #fecaca; }
.banner-success { background: #ecfdf5; color: #166534; border: 1px solid #bbf7d0; }
.gate-card { padding: 1.35rem; border-radius: 18px; border: 1px solid; display: grid; gap: .8rem; }
.gate-card.allowed { background: linear-gradient(135deg, #ecfdf5, #f0fdfa); border-color: #6ee7b7; }
.gate-card.blocked { background: linear-gradient(135deg, #fff7ed, #fff1f2); border-color: #fdba74; }
.gate-card h2 { margin: .25rem 0 0; }
.eyebrow { font-size: .76rem; text-transform: uppercase; letter-spacing: .08em; color: #64748b; }
.gate-meta { display: flex; flex-wrap: wrap; gap: 1rem; color: #475569; font-family: ui-monospace, monospace; font-size: .82rem; }
.reason-list { margin: 0; padding-left: 1.25rem; columns: 2; color: #9a3412; }
.boundary { margin: 0; font-size: .82rem; color: #64748b; }
.evidence-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: .75rem; }
.evidence-grid article { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1rem; display: grid; gap: .25rem; }
.evidence-grid b { font-size: 1.45rem; color: #0f172a; }
.evidence-grid span { color: #64748b; font-size: .8rem; }
.evidence-section { display: grid; gap: 1rem; }
.section-heading { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
.section-heading > div { display: flex; align-items: center; gap: .7rem; }
.section-heading h2 { margin: 0; font-size: 1.1rem; }
.step { display: grid; place-items: center; width: 2rem; height: 2rem; border-radius: 50%; background: #0f172a; color: #fff; font-size: .78rem; }
.hash-box { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px; padding: .75rem; display: grid; gap: .35rem; }
.hash-box span { color: #64748b; font-size: .78rem; }
.hash-box code { overflow-wrap: anywhere; color: #0f766e; }
.artifact-list, .record-list { display: grid; gap: .55rem; }
.artifact-row, .record-row { display: grid; grid-template-columns: minmax(180px, 1.1fr) minmax(180px, 1fr) minmax(100px, .5fr) auto; gap: .8rem; align-items: center; padding: .75rem; border: 1px solid #e2e8f0; border-radius: 10px; }
.artifact-row > div, .record-row > div { display: flex; align-items: center; gap: .55rem; flex-wrap: wrap; }
.record-row small { display: block; width: 100%; color: #64748b; }
.record-row code, .artifact-row code { overflow-wrap: anywhere; font-size: .72rem; color: #475569; }
.status { font-size: .72rem; border-radius: 999px; padding: .2rem .55rem; background: #e2e8f0; width: fit-content; }
.status[data-status='active'], .status[data-status='verified'], .status[data-status='certified'], .status[data-status='accepted'], .status[data-status='released'] { background: #dcfce7; color: #166534; }
.status[data-status='revoked'], .status[data-status='rejected'] { background: #fee2e2; color: #991b1b; }
.action-panel { border: 1px solid #cbd5e1; border-radius: 12px; padding: .8rem; background: #f8fafc; }
.action-panel summary { cursor: pointer; font-weight: 700; color: #0f172a; }
.action-panel textarea { width: 100%; box-sizing: border-box; margin: .8rem 0; padding: .8rem; border: 1px solid #94a3b8; border-radius: 10px; background: #0f172a; color: #e2e8f0; font: .78rem/1.5 ui-monospace, monospace; resize: vertical; }
.action-panel label { display: grid; gap: .35rem; margin-top: .8rem; font-size: .82rem; }
.action-panel input { padding: .65rem; border: 1px solid #94a3b8; border-radius: 8px; }
.inline-actions { justify-content: flex-end; }
.warning-note { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; padding: .8rem; border-radius: 10px; }
.admin-zone { border-color: #c4b5fd; }
.release-zone { border-color: #5eead4; }
.revoke-zone { border-color: #fca5a5; }
.revoke-form { display: grid; grid-template-columns: 1fr 1.4fr 2fr auto; gap: .7rem; align-items: end; }
.revoke-form label { display: grid; gap: .35rem; font-size: .78rem; color: #475569; }
.revoke-form input, .revoke-form select { padding: .65rem; border: 1px solid #94a3b8; border-radius: 8px; background: #fff; }
.sm { padding: .4rem .65rem; font-size: .75rem; }
@media (max-width: 900px) {
  .evidence-grid { grid-template-columns: repeat(2, 1fr); }
  .artifact-row, .record-row { grid-template-columns: 1fr; }
  .reason-list { columns: 1; }
  .delivery-header, .section-heading { align-items: stretch; flex-direction: column; }
  .revoke-form { grid-template-columns: 1fr; }
}
</style>
