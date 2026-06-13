import { useState, useCallback, useEffect, useRef } from 'react'
import { streamChat } from '../api/client'
import type { ChatMessage, ChatSession, QueryRequest } from '../types'

const SESSIONS_KEY = 'rag_chat_sessions'
const SETTINGS_KEY = 'rag_app_settings'

let msgCounter = 0
function nextMsgId() { return `msg-${++msgCounter}` }
function newSessionId() { return `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }

function readQuerySettings(): { topK: number; threshold: number } {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return {
      topK: typeof parsed.topK === 'number' ? parsed.topK : 5,
      threshold: typeof parsed.threshold === 'number' ? parsed.threshold : 0.3,
    }
  } catch {
    return { topK: 5, threshold: 0.3 }
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

/**
 * Manages chat sessions and messages.
 *
 * Session list and messages are persisted to localStorage so they survive page
 * refreshes. sendMessage uses the SSE streaming endpoint so tokens appear in
 * the UI as they are generated.
 */
export function useChat() {
  const [sessions, setSessions] = useState<ChatSession[]>(readSessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    const stored = readSessions()
    return stored.length > 0 ? stored[0].id : null
  })
  // Tracks whether a streaming request is in-flight for the active session.
  const [isActive, setIsActive] = useState(false)

  const sessionsRef = useRef(sessions)
  useEffect(() => { sessionsRef.current = sessions }, [sessions])

  const messages: ChatMessage[] =
    sessions.find((s) => s.id === activeSessionId)?.messages ?? []

  // ── Internal updater ───────────────────────────────────────────────────────

  /**
   * Apply an updater to one session's messages.
   * Pass persist=false during streaming to skip localStorage writes until done.
   */
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

  const searchSessions = useCallback((query: string): ChatSession[] => {
    if (!query.trim()) return sessionsRef.current
    const q = query.toLowerCase()
    return sessionsRef.current.filter((s) => s.title.toLowerCase().includes(q))
  }, [])

  // ── Chat ───────────────────────────────────────────────────────────────────

  const sendMessage = useCallback(
    async (question: string, documentId?: string) => {
      if (!question.trim()) return

      // Ensure there is an active session.
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

      // Auto-title from the first user message.
      setSessions((prev) => {
        const session = prev.find((s) => s.id === sessionId)
        if (!session || session.title !== 'New Chat') return prev
        const next = prev.map((s) =>
          s.id === sessionId ? { ...s, title: titleFromMessage(question) } : s
        )
        writeSessions(next)
        return next
      })

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

      try {
        const { topK, threshold } = readQuerySettings()
        const payload: QueryRequest = {
          question: question.trim(),
          top_k: topK,
          score_threshold: threshold,
          document_id: documentId,
        }

        let gotFirstToken = false

        for await (const event of streamChat(payload)) {
          if (event.type === 'token') {
            if (!gotFirstToken) {
              gotFirstToken = true
              // Transition: loading spinner → live streaming bubble.
              patchSessionMessages(
                sessionId,
                (msgs) =>
                  msgs.map((m) =>
                    m.id === loadingId
                      ? { ...m, isLoading: false, isStreaming: true, content: event.content }
                      : m
                  ),
                false, // don't persist yet — wait until streaming is complete
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
              true, // persist final state to localStorage
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
      } finally {
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
    isLoading: isActive,
    sessions,
    activeSessionId,
    createSession,
    loadSession,
    deleteSession,
    renameSession,
    searchSessions,
  }
}
