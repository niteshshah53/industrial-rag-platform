import type {
  DocumentRecord,
  DocumentStatus,
  UploadResponse,
  QueryRequest,
  QueryResponse,
} from '../types'

// In Docker: nginx strips /api prefix → forwards to http://app:8000
// In local dev: Vite proxy strips /api prefix → forwards to http://localhost:8000
const API_BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body?.detail?.message ?? body?.detail ?? body?.message ?? detail
    } catch {
      // ignore JSON parse errors — keep the HTTP status message
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// The backend returns status values in UPPERCASE (e.g. "READY").
// Normalize to lowercase so component comparisons work correctly.
function normalizeDoc(doc: DocumentRecord): DocumentRecord {
  return { ...doc, status: doc.status.toLowerCase() as DocumentStatus }
}

// ── Document endpoints ─────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await request<UploadResponse>('/v1/documents/upload', {
    method: 'POST',
    body: form,
  })
  return { ...res, status: res.status.toLowerCase() as DocumentStatus }
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const res = await request<{ documents: DocumentRecord[]; total: number }>('/v1/documents')
  return res.documents.map(normalizeDoc)
}

export async function getDocument(id: string): Promise<DocumentRecord> {
  const doc = await request<DocumentRecord>(`/v1/documents/${id}`)
  return normalizeDoc(doc)
}

export async function deleteDocument(id: string): Promise<void> {
  await request<unknown>(`/v1/documents/${id}`, { method: 'DELETE' })
}

// ── Chat endpoint ──────────────────────────────────────────────────────────────

export async function queryChat(payload: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>('/v1/chat/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
