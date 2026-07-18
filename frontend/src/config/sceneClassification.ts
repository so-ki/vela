import type {
  CapabilityPackDisplay,
  CapabilityPackIdentity,
  RulesCatalog,
  RulesClassification,
  ScenarioScopeProposal,
  ScenarioScopeSnapshot,
  SceneDefaults,
} from '@/types/scenario'

/** Catalog 缺失时保持空值，禁止浏览器冒充后端权威场景。 */
const EMPTY_SCENE_DEFAULTS: SceneDefaults = {
  rules_pack_id: '',
  country: '',
  state: '',
  city: '',
  industry: '',
  action_type: '',
}

export function sceneDefaultsFromCatalog(catalog: RulesCatalog | null | undefined): SceneDefaults {
  const capabilityPack = capabilityPackFromCatalog(catalog)
  if (catalog?.scene_defaults) {
    return {
      rules_pack_id: catalog.rules_pack_id || catalog.scene_defaults.rules_pack_id || '',
      country: capabilityPack?.country || catalog.scene_defaults.country || '',
      state: catalog.scene_defaults.state || '',
      city: catalog.scene_defaults.city || '',
      industry: capabilityPack?.industry || catalog.scene_defaults.industry || '',
      action_type: capabilityPack?.action_type || catalog.scene_defaults.action_type || '',
    }
  }
  if (catalog?.pack?.id) {
    const loc = catalog.supported_locations?.[0]
    return {
      rules_pack_id: catalog.rules_pack_id || catalog.pack.id,
      country: catalog.pack.primary_country || catalog.jurisdiction?.id || '',
      state: loc?.state || '',
      city: loc?.city || '',
      industry: catalog.industries?.[0]?.id || '',
      action_type: catalog.action_types?.[0]?.id || '',
    }
  }
  return { ...EMPTY_SCENE_DEFAULTS }
}

export function regionLabelForCatalog(catalog: RulesCatalog | null | undefined): string {
  const region = catalog?.pack?.region
  if (region === 'latin_america') return '拉美'
  return region || '拉美'
}

export function countryLabelForCatalog(catalog: RulesCatalog | null | undefined): string {
  return catalog?.jurisdiction?.name || '未加载'
}

export function defaultPackFromClassification(classification: RulesClassification | null | undefined): string {
  return classification?.default_pack_id || ''
}

function hasIdentityString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function capabilityPackFromCatalog(
  catalog: RulesCatalog | null | undefined,
): CapabilityPackIdentity | null {
  const pack = catalog?.capability_pack
  if (
    !pack ||
    pack.status !== 'active' ||
    !hasIdentityString(pack.pack_id) ||
    !hasIdentityString(pack.version) ||
    !hasIdentityString(pack.pack_hash) ||
    !hasIdentityString(pack.display_name) ||
    !hasIdentityString(pack.country) ||
    !hasIdentityString(pack.state) ||
    !hasIdentityString(pack.industry) ||
    !hasIdentityString(pack.action_type) ||
    !Array.isArray(pack.languages)
  ) {
    return null
  }
  return pack
}

export function isUsableCapabilityCatalog(
  catalog: RulesCatalog | null | undefined,
): catalog is RulesCatalog {
  return capabilityPackFromCatalog(catalog) !== null
}

export function catalogMatchesProposal(
  catalog: RulesCatalog | null | undefined,
  proposal: ScenarioScopeProposal | null | undefined,
): boolean {
  const pack = capabilityPackFromCatalog(catalog)
  return !!(
    pack &&
    proposal &&
    pack.pack_id === proposal.pack_id &&
    pack.version === proposal.pack_version &&
    pack.pack_hash === proposal.pack_hash
  )
}

export function catalogMatchesSnapshot(
  catalog: RulesCatalog | null | undefined,
  snapshot: ScenarioScopeSnapshot | null | undefined,
): boolean {
  const pack = capabilityPackFromCatalog(catalog)
  return !!(
    pack &&
    snapshot &&
    pack.pack_id === snapshot.capability_pack_id &&
    pack.version === snapshot.capability_pack_version &&
    pack.pack_hash === snapshot.capability_pack_hash
  )
}

export function capabilityPackFromProposal(
  proposal: ScenarioScopeProposal | null | undefined,
  catalog?: RulesCatalog | null,
): CapabilityPackDisplay | null {
  if (!proposal?.pack_id || !proposal.pack_version || !proposal.pack_hash) return null
  const matchedCatalog = catalogMatchesProposal(catalog, proposal)
    ? capabilityPackFromCatalog(catalog)
    : null
  return {
    pack_id: proposal.pack_id,
    version: proposal.pack_version,
    pack_hash: proposal.pack_hash,
    status: matchedCatalog ? 'active' : 'unverified',
    display_name: proposal.labels?.pack || matchedCatalog?.display_name || proposal.pack_id,
    description: matchedCatalog?.description,
    content_status: matchedCatalog?.content_status,
    country: proposal.labels?.country || proposal.country,
    state: matchedCatalog?.state || proposal.state,
    industry: proposal.labels?.industry || proposal.industry,
    action_type: proposal.labels?.action_type || proposal.action_type,
    languages: matchedCatalog?.languages,
  }
}

export function capabilityPackFromSnapshot(
  snapshot: ScenarioScopeSnapshot | null | undefined,
  proposal?: ScenarioScopeProposal | null,
): CapabilityPackDisplay | null {
  if (
    !snapshot?.capability_pack_id ||
    !snapshot.capability_pack_version ||
    !snapshot.capability_pack_hash
  ) {
    return null
  }
  const labels = snapshot.audit_metadata?.labels || proposal?.labels
  return {
    pack_id: snapshot.capability_pack_id,
    version: snapshot.capability_pack_version,
    pack_hash: snapshot.capability_pack_hash,
    status: 'frozen',
    display_name: labels?.pack || snapshot.capability_pack_id,
    country: labels?.country || snapshot.country,
    state: snapshot.state,
    industry: labels?.industry || snapshot.industry,
    action_type: labels?.action_type || snapshot.action_type,
  }
}
