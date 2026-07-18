import { describe, expect, it } from 'vitest'

import router from './index'

describe('Legal Playbook route access', () => {
  it('marks cold-start as legal-only', () => {
    const route = router.getRoutes().find((candidate) => candidate.name === 'cold-start')
    expect(route?.meta.legalOnly).toBe(true)
  })

  it('exposes the mechanism workbench to authenticated business and legal roles', () => {
    const route = router.getRoutes().find((candidate) => candidate.name === 'mechanism')
    expect(route?.meta.requiresDisclaimer).toBe(true)
    expect(route?.meta.mechanismAccess).toBe(true)
    expect(route?.meta.legalOnly).toBeUndefined()
    expect(route?.meta.businessOnly).toBeUndefined()
  })

  it('exposes the customer delivery evidence console to every authenticated scenario participant', () => {
    const route = router.getRoutes().find((candidate) => candidate.name === 'delivery-assurance')
    expect(route?.meta.requiresDisclaimer).toBe(true)
    expect(route?.meta.legalOnly).toBeUndefined()
    expect(route?.meta.businessOnly).toBeUndefined()
  })
})
