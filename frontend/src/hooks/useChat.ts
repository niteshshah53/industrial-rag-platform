import { useState, useCallback, useEffect, useRef } from 'react'
import { streamChat } from '../api/client'
import type { ChatMessage, ChatSession, ConversationTurn, QueryRequest } from '../types'

const SESSIONS_KEY = 'rag_chat_sessions'
const SETTINGS_KEY = 'rag_app_settings'

function nextMsgId() {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}
function newSessionId() { return `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }

function readQuerySettings(): { topK: number; threshold: number; searchMode: 'dense' | 'hybrid' } {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return {
      topK: typeof parsed.topK === 'number' ? parsed.topK : 5,
      threshold: typeof parsed.threshold === 'number' ? parsed.threshold : 0.3,
      searchMode: parsed.searchMode === 'dense' ? 'dense' : 'hybrid',
    }
  } catch {
    return { topK: 5, threshold: 0.3, searchMode: 'hybrid' }
  }
}

// ── Storage helpers ────────────────────────────────────────────────────────────

function readSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY)
    return raw ? (JSON.parse(raw) as ChatSession[]) : []
  } catch {
    return []
  }
}

function writeSessions(sessions: ChatSession[]): void {
  try {
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions))
  } catch {}
}

function titleFromMessage(content: string): string {
  return content.trim().slice(0, 40) || 'New Chat'
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useChat() {
  const [sessions, setSessions] = useState<ChatSession[]>(readSessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    const stored = readSessions()
    return stored.length > 0 ? stored[0].id : null
  })
  const [isActive, setIsActive] = useState(false)

  const sessionsRef = useRef(sessions)
  useEffect(() => { sessionsRef.current = sessions }, [sessions])

  // Tracks the AbortController for the current streaming request.
  const abortRef = useRef<AbortController | null>(null)

  const messages: ChatMessage[] =
    sessions.find((s) => s.id === activeSessionId)?.messages ?? []

  // ── Internal updater ───────────────────────────────────────────────────────

  const patchSessionMessages = useCallback(
    (sessionId: string, updater: (msgs: ChatMessage[]) => ChatMessage[], persist = true) => {
      setSessions((prev) => {
        const next = prev.map((s) =>
          s.id === sessionId
            ? { ...s, messages: updater(s.messages), updatedAt: new Date().toISOString() }
            : s
        )
        if (persist) writeSessions(next)
        return next
      })
    },
    []
  )

  // ── Session management ─────────────────────────────────────────────────────

  const createSession = useCallback((documentId?: string): string => {
    const id = newSessionId()
    const now = new Date().toISOString()
    const session: ChatSession = {
      id,
      title: 'New Chat',
      createdAt: now,
      updatedAt: now,
      messages: [],
      documentId,
    }
    setSessions((prev) => {
      const next = [session, ...prev]
      writeSessions(next)
      return next
    })
    setActiveSessionId(id)
    return id
  }, [])

  const loadSession = useCallback((id: string) => {
    setActiveSessionId(id)
  }, [])

  const deleteSession = useCallback((id: string) => {
    const remaining = sessionsRef.current.filter((s) => s.id !== id)
    setSessions(() => {
      writeSessions(remaining)
      return remaining
    })
    setActiveSessionId((prev) => {
      if (prev !== id) return prev
      return remaining.length > 0 ? remaining[0].id : null
    })
  }, [])

  const renameSession = useCallback((id: string, title: string) => {
    setSessions((prev) => {
      const next = prev.map((s) =>
        s.id === id ? { ...s, title, updatedAt: new Date().toISOString() } : s
      )
      writeSessions(next)
      return next
    })
  }, [])

  const pinSession = useCallback((id: string) => {
    setSessions((prev) => {
      const next = prev.map((s) => s.id === id ? { ...s, isPinned: !s.isPinned } : s)
      writeSessions(next)
      return next
    })
  }, [])

  const archiveSession = useCallback((id: string) => {
    setSessions((prev) => {
      const next = prev.map((s) => s.id === id ? { ...s, isArchived: !s.isArchived, isPinned: false } : s)
      writeSessions(next)
      return next
    })
    // If we just archived the active session, switch to next available
    setActiveSessionId((prev) => {
      if (prev !== id) return prev
      const remaining = sessionsRef.current.filter((s) => s.id !== id && !s.isArchived)
      return remaining.length > 0 ? remaining[0].id : null
    })
  }, [])

  const searchSessions = useCallback((query: string): ChatSession[] => {
    if (!query.trim()) return sessionsRef.current
    const q = query.toLowerCase()
    return sessionsRef.current.filter((s) => s.title.toLowerCase().includes(q))
  }, [])

  // ── Message operations ─────────────────────────────────────────────────────

  const deleteMessage = useCallback((msgId: string) => {
    if (!activeSessionId) return
    patchSessionMessages(activeSessionId, (msgs) => msgs.filter((m) => m.id !== msgId))
  }, [activeSessionId, patchSessionMessages])

  /** Delete msgId and every message after it in the current session. */
  const truncateFrom = useCallback((msgId: string) => {
    if (!activeSessionId) return
    patchSessionMessages(activeSessionId, (msgs) => {
      const idx = msgs.findIndex((m) => m.id === msgId)
      return idx >= 0 ? msgs.slice(0, idx) : msgs
    })
  }, [activeSessionId, patchSessionMessages])

  const reactToMessage = useCallback((msgId: string, reaction: 'like' | 'dislike') => {
    if (!activeSessionId) return
    patchSessionMessages(activeSessionId, (msgs) =>
      msgs.map((m) =>
        m.id === msgId ? { ...m, reaction: m.reaction === reaction ? undefined : reaction } : m
      )
    )
  }, [activeSessionId, patchSessionMessages])

  // ── Stop generation ────────────────────────────────────────────────────────

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  // ── Chat ───────────────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (question: string, documentId?: string, collectionId?: string) => {
      if (!question.trim()) return

      let sid = activeSessionId
      if (!sid) {
        sid = newSessionId()
        const now = new Date().toISOString()
        const session: ChatSession = {
          id: sid,
          title: titleFromMessage(question),
          createdAt: now,
          updatedAt: now,
          messages: [],
          documentId,
        }
        setSessions((prev) => {
          const next = [session, ...prev]
          writeSessions(next)
          return next
        })
        setActiveSessionId(sid)
      }

      const sessionId = sid

      setSessions((prev) => {
        const session = prev.find((s) => s.id === sessionId)
        if (!session || session.title !== 'New Chat') return prev
        const next = prev.map((s) =>
          s.id === sessionId ? { ...s, title: titleFromMessage(question) } : s
        )
        writeSessions(next)
        return next
      })

      const MAX_HISTORY = 6
      const priorMsgs = sessionsRef.current
        .find((s) => s.id === sessionId)?.messages ?? []
      const history: ConversationTurn[] = priorMsgs
        .filter((m) => !m.isLoading && !m.isStreaming && !m.isError && m.content)
        .slice(-MAX_HISTORY)
        .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))

      const userMsg: ChatMessage = {
        id: nextMsgId(),
        role: 'user',
        content: question.trim(),
      }
      const loadingId = nextMsgId()
      const loadingMsg: ChatMessage = {
        id: loadingId,
        role: 'assistant',
        content: '',
        isLoading: true,
      }

      patchSessionMessages(sessionId, (msgs) => [...msgs, userMsg, loadingMsg])
      setIsActive(true)

      // Create a fresh AbortController for this request.
      const controller = new AbortController()
      abortRef.current = controller

      try {
        const { topK, threshold, searchMode } = readQuerySettings()
        const payload: QueryRequest = {
          question: question.trim(),
          top_k: topK,
          score_threshold: threshold,
          document_id: collectionId ? undefined : documentId,
          collection_id: collectionId,
          search_mode: searchMode,
          conversation_history: history,
        }

        let gotFirstToken = false

        for await (const event of streamChat(payload, controller.signal)) {
          if (event.type === 'token') {
            if (!gotFirstToken) {
              gotFirstToken = true
              patchSessionMessages(
                sessionId,
                (msgs) =>
                  msgs.map((m) =>
                    m.id === loadingId
                      ? { ...m, isLoading: false, isStreaming: true, content: event.content }
                      : m
                  ),
                false,
              )
            } else {
              patchSessionMessages(
                sessionId,
                (msgs) =>
                  msgs.map((m) =>
                    m.id === loadingId
                      ? { ...m, content: m.content + event.content }
                      : m
                  ),
                false,
              )
            }
          } else if (event.type === 'done') {
            patchSessionMessages(
              sessionId,
              (msgs) =>
                msgs.map((m) =>
                  m.id === loadingId
                    ? {
                        id: loadingId,
                        role: 'assistant',
                        content: event.answer,
                        citations: event.citations,
                        latency_ms: event.latency_ms,
                        isLoading: false,
                        isStreaming: false,
                      }
                    : m
                ),
              true,
            )
          } else if (event.type === 'error') {
            patchSessionMessages(
              sessionId,
              (msgs) =>
                msgs.map((m) =>
                  m.id === loadingId
                    ? {
                        id: loadingId,
                        role: 'assistant',
                        content: event.message,
                        isLoading: false,
                        isStreaming: false,
                        isError: true,
                      }
                    : m
                ),
              true,
            )
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          // User stopped generation — mark message as stopped with whatever content streamed so far.
          patchSessionMessages(
            sessionId,
            (msgs) =>
              msgs.map((m) =>
                m.id === loadingId
                  ? { ...m, isLoading: false, isStreaming: false, isStopped: true }
                  : m
              ),
            true,
          )
        } else {
          const errorText = err instanceof Error ? err.message : 'Something went wrong.'
          patchSessionMessages(
            sessionId,
            (msgs) =>
              msgs.map((m) =>
                m.id === loadingId
                  ? { id: loadingId, role: 'assistant', content: errorText, isLoading: false, isStreaming: false, isError: true }
                  : m
              ),
            true,
          )
        }
      } finally {
        abortRef.current = null
        setIsActive(false)
      }
    },
    [activeSessionId, patchSessionMessages]
  )

  const clearMessages = useCallback(() => {
    if (activeSessionId) patchSessionMessages(activeSessionId, () => [])
  }, [activeSessionId, patchSessionMessages])

  return {
    messages,
    sendMessage,
    clearMessages,
    stopGeneration,
    isLoading: isActive,
    sessions,
    activeSessionId,
    createSession,
    loadSession,
    deleteSession,
    renameSession,
    pinSession,
    archiveSession,
    searchSessions,
    deleteMessage,
    truncateFrom,
    reactToMessage,
  }
}
