import { describe, expect, it } from 'vitest'

import router from './index'

describe('Legal Playbook route access', () => {
  it('marks cold-start as legal-only', () => {
    const route = router.getRoutes().find((candidate) => candidate.name === 'cold-start')
    expect(route?.meta.legalOnly).toBe(true)
  })
})
