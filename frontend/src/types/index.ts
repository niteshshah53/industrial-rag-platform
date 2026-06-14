// TypeScript mirrors of the backend Pydantic models.
// Keep in sync with app/core/models.py.

export type DocumentStatus = 'PENDING' | 'PROCESSING' | 'READY' | 'FAILED'

export interface DocumentRecord {
  document_id: string
  filename: string
  file_hash: string
  status: DocumentStatus
  file_size_bytes: number
  chunk_count: number
  error_message: string | null
  upload_timestamp: string
}

export interface UploadResponse {
  document_id: string
  filename: string
  status: DocumentStatus
}

export interface Citation {
  document_name: string
  page_number: number
  chunk_index: number
  relevance_score: number
  snippet?: string
  text?: string
}

export interface QueryResponse {
  answer: string
  citations: Citation[]
  retrieval_count: number
  context_chunks_used: number
  latency_ms: number
}

export interface ConversationTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface QueryRequest {
  question: string
  top_k?: number
  score_threshold?: number
  document_id?: string
  collection_id?: string
  search_mode?: 'dense' | 'hybrid'
  conversation_history?: ConversationTurn[]
}

// ── Collection types ───────────────────────────────────────────────────────────

export interface Collection {
  collection_id: string
  name: string
  description: string | null
  document_ids: string[]
  created_at: string
}

export interface CollectionCreate {
  name: string
  description?: string
  document_ids?: string[]
}

export interface CollectionListResponse {
  collections: Collection[]
  total: number
}

// ── UI-only types ──────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  citations?: Citation[]
  latency_ms?: number
  isLoading?: boolean
  isStreaming?: boolean
  isError?: boolean
  isStopped?: boolean
  reaction?: 'like' | 'dislike'
}

export interface ChatSession {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messages: ChatMessage[]
  documentId?: string
  isPinned?: boolean
  isArchived?: boolean
}

export type Theme = 'light' | 'dark' | 'system'

export interface AppSettings {
  topK: number
  threshold: number
  theme: Theme
  searchMode: 'dense' | 'hybrid'
}
