export const COMPETITION_MODE = 'competition'

export function isCompetitionMode(): boolean {
  return import.meta.env.VITE_APP_MODE === COMPETITION_MODE
}

export function competitionScenarioId(): number | null {
  const raw = import.meta.env.VITE_COMPETITION_SCENARIO_ID
  if (!raw) return null
  const value = Number(raw)
  return Number.isInteger(value) && value > 0 ? value : null
}

export function competitionOverviewPath(): string {
  const scenarioId = competitionScenarioId()
  if (scenarioId === null) {
    throw new Error('competition mode requires VITE_COMPETITION_SCENARIO_ID')
  }
  return `/competition/${scenarioId}/overview`
}
