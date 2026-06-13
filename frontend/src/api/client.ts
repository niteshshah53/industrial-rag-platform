import type {
  DocumentRecord,
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

// ── Document endpoints ─────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return request<UploadResponse>('/v1/documents/upload', {
    method: 'POST',
    body: form,
  })
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const res = await request<{ documents: DocumentRecord[]; total: number }>('/v1/documents')
  return res.documents
}

export async function getDocument(id: string): Promise<DocumentRecord> {
  return request<DocumentRecord>(`/v1/documents/${id}`)
}

export async function deleteDocument(id: string): Promise<void> {
  await request<unknown>(`/v1/documents/${id}`, { method: 'DELETE' })
}

// ── Chat endpoints ─────────────────────────────────────────────────────────────

export async function queryChat(payload: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>('/v1/chat/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// SSE event shapes emitted by POST /v1/chat/stream
export type StreamEvent =
  | { type: 'token'; content: string }
  | {
      type: 'done'
      answer: string
      citations: QueryResponse['citations']
      retrieval_count: number
      context_chunks_used: number
      latency_ms: number
      request_id: string
    }
  | { type: 'error'; message: string }

/**
 * Async generator that POSTs to /v1/chat/stream and yields parsed SSE events.
 *
 * Reads the response body as a ReadableStream, decodes NDJSON-style
 * ``data: {json}\n\n`` lines, and yields typed StreamEvent objects.
 */
export async function* streamChat(
  payload: QueryRequest,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/v1/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body?.detail?.message ?? body?.detail ?? body?.message ?? detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by double newlines.
    const parts = buffer.split('\n\n')
    // Keep the last (possibly incomplete) chunk in the buffer.
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) continue
      try {
        yield JSON.parse(jsonStr) as StreamEvent
      } catch {
        // Malformed SSE line — skip silently.
      }
    }
  }
}
