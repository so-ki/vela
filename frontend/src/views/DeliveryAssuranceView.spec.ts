import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DeliveryAssuranceView from './DeliveryAssuranceView.vue'
import { makeScenario } from '@/test/factories'

const client = vi.hoisted(() => ({
  decideExpertSignature: vi.fn(),
  decideLegalCredential: vi.fn(),
  downloadCandidateArtifact: vi.fn(),
  fetchDeliveryArtifactManifest: vi.fn(),
  fetchDeliveryArtifacts: vi.fn(),
  fetchDeliveryGateStatus: vi.fn(),
  fetchDeliveryReleases: vi.fn(),
  fetchDeploymentEvidence: vi.fn(),
  fetchExpertAttestations: vi.fn(),
  fetchLegalContentCertifications: vi.fn(),
  fetchLegalCredentials: vi.fn(),
  fetchScenario: vi.fn(),
  fetchUATAcceptances: vi.fn(),
  freezeDeliveryArtifacts: vi.fn(),
  previewLegalContentManifest: vi.fn(),
  revokeDeliveryRelease: vi.fn(),
  revokeDeploymentEvidence: vi.fn(),
  revokeExpertAttestation: vi.fn(),
  revokeLegalContentCertification: vi.fn(),
  submitDeliveryRelease: vi.fn(),
  submitDeploymentEvidence: vi.fn(),
  submitExpertAttestation: vi.fn(),
  submitLegalContentCertification: vi.fn(),
  submitLegalCredential: vi.fn(),
  submitUATAcceptance: vi.fn(),
  withdrawUATAcceptance: vi.fn(),
}))

const auth = vi.hoisted(() => ({
  user: {
    id: 1,
    full_name: 'Customer Owner',
    organization: 'Acme',
    role: 'business',
  },
}))

vi.mock('@/api/client', () => client)
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('vue-router', async () => {
  const vue = await import('vue')
  return {
    RouterLink: vue.defineComponent({ template: '<a><slot /></a>' }),
    useRoute: () => ({ params: { id: '9' } }),
  }
})

const artifact = {
  id: 'artifact-docx',
  scenario_id: 9,
  artifact_type: 'docx',
  snapshot_hash: 's'.repeat(64),
  content_sha256: 'a'.repeat(64),
  content_length: 1024,
  media_type: 'application/octet-stream',
  filename: 'candidate.docx',
  renderer_version: 'test',
  status: 'candidate',
  created_by: 2,
  created_at: '2026-07-18T00:00:00Z',
}

const pendingAttestation = {
  id: 'attestation-1',
  scenario_id: 9,
  credential_id: 'credential-1',
  signed_by: 2,
  snapshot_hash: 's'.repeat(64),
  artifact_manifest_hash: 'm'.repeat(64),
  signature_format: 'PAdES',
  signature_validation_status: 'submitted',
  signature_verified_by: null,
  status: 'pending_validation',
  signed_at: '2026-07-18T00:00:00Z',
  expires_at: '2026-08-18T00:00:00Z',
}

describe('DeliveryAssuranceView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    auth.user = {
      id: 1,
      full_name: 'Customer Owner',
      organization: 'Acme',
      role: 'business',
    }
    client.fetchScenario.mockResolvedValue(makeScenario({ status: 'review_approved' }))
    client.fetchDeliveryGateStatus.mockResolvedValue({
      schema_version: '1.0',
      scenario_id: 9,
      evaluated_at: '2026-07-18T00:00:00Z',
      delivery_allowed: false,
      blocking_reasons: ['active_delivery_release_missing'],
      snapshot_hash: 's'.repeat(64),
      release_id: null,
      release_hash: null,
      expert_attestation_id: null,
      uat_acceptance_id: null,
      deployment_evidence_id: null,
      boundary: '外部证据尚未进入系统',
    })
    client.fetchDeliveryArtifacts.mockResolvedValue([artifact])
    client.fetchDeliveryArtifactManifest.mockResolvedValue({
      scenario_id: 9,
      snapshot_hash: 's'.repeat(64),
      artifact_manifest: [],
      artifact_manifest_hash: 'm'.repeat(64),
    })
    client.fetchExpertAttestations.mockResolvedValue([pendingAttestation])
    client.fetchUATAcceptances.mockResolvedValue([])
    client.fetchDeliveryReleases.mockResolvedValue([])
    client.fetchLegalCredentials.mockResolvedValue([])
    client.fetchLegalContentCertifications.mockResolvedValue([])
    client.fetchDeploymentEvidence.mockResolvedValue([])
    client.decideExpertSignature.mockResolvedValue({
      ...pendingAttestation,
      status: 'active',
      signature_validation_status: 'approved',
    })
  })

  it('shows business the exact candidate/UAT path without release-admin controls', async () => {
    const wrapper = mount(DeliveryAssuranceView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('当前禁止客户交付')
    expect(wrapper.text()).toContain('active_delivery_release_missing')
    expect(wrapper.text()).toContain('canonical artifact manifest hash')
    expect(wrapper.text()).toContain('由场景提交人签署 UAT')
    expect(wrapper.text()).not.toContain('双律师内容认证与生产证据')
    expect(client.fetchLegalCredentials).not.toHaveBeenCalled()
  })

  it('lets admin independently decide a pending signature and exposes production evidence controls', async () => {
    auth.user = {
      id: 3,
      full_name: 'Release Admin',
      organization: 'Acme',
      role: 'admin',
    }
    const wrapper = mount(DeliveryAssuranceView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('双律师内容认证与生产证据')
    expect(wrapper.text()).toContain('创建限时客户交付 release')
    const approve = wrapper
      .findAll('button')
      .find((button) => button.text().includes('批准 VALIDAR 核验'))
    expect(approve).toBeDefined()
    await approve!.trigger('click')
    await flushPromises()

    expect(client.decideExpertSignature).toHaveBeenCalledWith(9, 'attestation-1', {
      decision: 'approved',
      note: expect.stringContaining('ITI VALIDAR'),
    })
    expect(client.fetchDeploymentEvidence).toHaveBeenCalled()
  })

  it('blocks a signature verifier from approving the same final release', async () => {
    auth.user = {
      id: 3,
      full_name: 'Release Admin',
      organization: 'Acme',
      role: 'admin',
    }
    client.fetchExpertAttestations.mockResolvedValue([
      {
        ...pendingAttestation,
        status: 'active',
        signature_validation_status: 'approved',
        signature_verified_by: 3,
      },
    ])
    const wrapper = mount(DeliveryAssuranceView, { global: { stubs: { RouterLink: true } } })
    await flushPromises()

    expect(wrapper.text()).toContain('当前账号参与了 场景签名核验')
    const releaseButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('重算并创建 release'))
    expect(releaseButton?.attributes('disabled')).toBeDefined()
  })
})
