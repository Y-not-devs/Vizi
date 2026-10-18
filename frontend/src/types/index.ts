/**
 * Типы данных Vizi.
 */

export interface EvidenceFrame {
  timestamp_sec: number
  image_base64: string
}

export interface Violation {
  type: string
  timecode_sec: number
  description: string
  rule?: string
  normative_source?: string
  confidence?: number
  motion_score?: number
  evidence_frames: EvidenceFrame[]
}

export type Verdict = 'violation' | 'no_violation'
export type JobStatus = 'processing' | 'done' | 'failed' | 'queued'

export interface AnalysisResponse {
  job_id: string
  status: JobStatus
  verdict?: Verdict
  violations?: Violation[]
  // Совместимость с дополнительными полями воркера бэкенда
  anomalies?: any[]
  total_duration_sec?: number
  processing_time_sec?: number
  processed_segments_count?: number
  error?: string
  video_path?: string
  raw_response?: any
}

export interface BackendMeta {
  app_name: string
  environment: string
  features?: {
    auth?: boolean
    uploads?: boolean
    ai?: boolean
  }
  status?: string
}

export interface AnalysisJobInit {
  job_id: string
  status?: JobStatus
  message?: string
}

export interface StandardRuleInfo {
  typeMatch: string
  ruleTitle: string
  documentName: string
  clause: string
  explanation: string
}
