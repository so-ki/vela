export interface CompetitionBusinessMaterial {
  id: string
  filename: string
  uploaded_at: string
  status: string
}

export interface CompetitionBusinessFact {
  id: string
  label: string
  value: string
  status: string
}

export interface CompetitionBusinessSupplement {
  id: string
  title: string
  why: string
  accepted_materials: string[]
  status: string
}

export interface CompetitionBusinessProgress {
  label: string
  state: 'completed' | 'current' | 'upcoming'
}

export interface CompetitionBusinessCenter {
  scenario_id: number
  project_name: string
  materials: CompetitionBusinessMaterial[]
  facts: CompetitionBusinessFact[]
  supplements: CompetitionBusinessSupplement[]
  progress: CompetitionBusinessProgress[]
  current_status: string
}
