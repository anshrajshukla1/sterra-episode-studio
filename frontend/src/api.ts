import { getIdToken } from './firebase'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function authHeaders(): Promise<Record<string, string>> {
  const token = await getIdToken()
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

export interface Recording {
  id: string
  filename: string
  size_bytes: number
  duration_s: number | null
  stream_names: string[] | null
  status: 'unprocessed' | 'processing' | 'done' | 'error'
  error_msg: string | null
  created_at: string
}

export interface Job {
  id: string
  recording_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_msg: string | null
}

export interface Result {
  id: string
  job_id: string
  episode_path: string
  report_path: string
  health_score: number | null
  metadata_json: {
    duration_s: number
    frame_count: number
    stream_names: string[]
    has_depth: boolean
    has_pose: boolean
  }
  created_at: string
}

export const api = {
  async getRecordings(): Promise<Recording[]> {
    const res = await fetch(`${API_BASE}/api/recordings`, {
      headers: await authHeaders(),
    })
    if (!res.ok) throw new Error(`Failed to fetch recordings: ${res.statusText}`)
    const data = await res.json()
    return data.items || []
  },

  async getRecording(id: string): Promise<Recording> {
    const res = await fetch(`${API_BASE}/api/recordings/${id}`, {
      headers: await authHeaders(),
    })
    if (!res.ok) throw new Error(`Recording not found: ${res.statusText}`)
    return res.json()
  },

  async createJob(recordingId: string): Promise<Job> {
    const res = await fetch(`${API_BASE}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...await authHeaders() },
      body: JSON.stringify({ recording_id: recordingId }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || 'Failed to create job')
    }
    return res.json()
  },

  async getJob(id: string): Promise<Job> {
    const res = await fetch(`${API_BASE}/api/jobs/${id}`, {
      headers: await authHeaders(),
    })
    if (!res.ok) throw new Error(`Job not found`)
    return res.json()
  },

  async getResult(jobId: string): Promise<Result> {
    const res = await fetch(`${API_BASE}/api/results/${jobId}`, {
      headers: await authHeaders(),
    })
    if (!res.ok) throw new Error(`Result not found`)
    return res.json()
  },

  async getAllResults(): Promise<Result[]> {
    const res = await fetch(`${API_BASE}/api/results`, {
      headers: await authHeaders(),
    })
    if (!res.ok) throw new Error(`Failed to fetch results`)
    return res.json()
  },

  getVideoUrl(jobId: string): string {
    return `${API_BASE}/api/files/${jobId}/video`
  },

  getReportUrl(jobId: string): string {
    return `${API_BASE}/api/files/${jobId}/report`
  },

  // SSE stream — returns EventSource (caller manages lifecycle)
  async createJobStream(jobId: string): Promise<EventSource> {
    const token = await getIdToken()
    const url = new URL(`${API_BASE}/api/jobs/${jobId}/stream`)
    if (token) url.searchParams.set('token', token)
    return new EventSource(url.toString())
  },
}
