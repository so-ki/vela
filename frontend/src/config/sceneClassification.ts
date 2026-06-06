import type { RulesCatalog, RulesClassification, SceneDefaults } from '@/types/scenario'

/** 离线回退：与 index.json default_pack 对齐 */
export const FALLBACK_SCENE_DEFAULTS: SceneDefaults = {
  rules_pack_id: 'brazil_new_energy',
  country: 'brazil',
  state: 'sao_paulo',
  city: 'campinas',
  industry: 'new_energy',
  action_type: 'greenfield_plant',
}

export function sceneDefaultsFromCatalog(catalog: RulesCatalog | null | undefined): SceneDefaults {
  if (catalog?.scene_defaults) {
    return {
      rules_pack_id: catalog.rules_pack_id || catalog.scene_defaults.rules_pack_id || FALLBACK_SCENE_DEFAULTS.rules_pack_id,
      country: catalog.scene_defaults.country || FALLBACK_SCENE_DEFAULTS.country,
      state: catalog.scene_defaults.state || FALLBACK_SCENE_DEFAULTS.state,
      city: catalog.scene_defaults.city || FALLBACK_SCENE_DEFAULTS.city,
      industry: catalog.scene_defaults.industry || FALLBACK_SCENE_DEFAULTS.industry,
      action_type: catalog.scene_defaults.action_type || FALLBACK_SCENE_DEFAULTS.action_type,
    }
  }
  if (catalog?.pack?.id) {
    const loc = catalog.supported_locations?.[0]
    return {
      rules_pack_id: catalog.rules_pack_id || catalog.pack.id,
      country: catalog.pack.primary_country || catalog.jurisdiction?.id || FALLBACK_SCENE_DEFAULTS.country,
      state: loc?.state || FALLBACK_SCENE_DEFAULTS.state,
      city: loc?.city || FALLBACK_SCENE_DEFAULTS.city,
      industry: catalog.industries?.[0]?.id || FALLBACK_SCENE_DEFAULTS.industry,
      action_type: catalog.action_types?.[0]?.id || FALLBACK_SCENE_DEFAULTS.action_type,
    }
  }
  return { ...FALLBACK_SCENE_DEFAULTS }
}

export function applySceneDefaults<T extends Record<string, unknown>>(
  payload: T,
  catalog: RulesCatalog | null | undefined,
): T {
  const defaults = sceneDefaultsFromCatalog(catalog)
  return {
    ...payload,
    rules_pack_id: payload.rules_pack_id || defaults.rules_pack_id,
    country: payload.country || defaults.country,
    state: payload.state || defaults.state,
    city: payload.city || defaults.city,
    industry: payload.industry || defaults.industry,
    action_type: payload.action_type || defaults.action_type,
  }
}

export function regionLabelForCatalog(catalog: RulesCatalog | null | undefined): string {
  const region = catalog?.pack?.region
  if (region === 'latin_america') return '拉美'
  return region || '拉美'
}

export function countryLabelForCatalog(catalog: RulesCatalog | null | undefined): string {
  return catalog?.jurisdiction?.name || '巴西'
}

export function defaultPackFromClassification(classification: RulesClassification | null | undefined): string {
  return classification?.default_pack_id || FALLBACK_SCENE_DEFAULTS.rules_pack_id
}
