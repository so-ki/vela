export interface User {
  id: number
  email: string
  full_name: string
  organization: string | null
  role: string
  is_active: boolean
  disclaimer_accepted: boolean
  disclaimer_accepted_at: string | null
  created_at: string
}

export interface DisclaimerSection {
  title: string
  content: string
}

export interface Disclaimer {
  title: string
  version: string
  sections: DisclaimerSection[]
  full_text: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface SystemStatus {
  database: string
  chroma: { status: string; collection?: string; document_count?: number; message?: string }
  disclaimer_required: boolean
}
