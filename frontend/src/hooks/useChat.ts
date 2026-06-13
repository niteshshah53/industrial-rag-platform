import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { queryChat } from '../api/client'
import type { ChatMessage, ChatSession, QueryRequest } from '../types'

const SESSIONS_KEY = 'rag_chat_sessions'
const SETTINGS_KEY = 'rag_app_settings'

let msgCounter = 0
function nextMsgId() { return `msg-${++msgCounter}` }
function newSessionId() { return `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }

// Read the latest retrieval settings from localStorage at call time so that
// slider changes in the settings panel are reflected in the very next query
// without needing to thread settings state through the entire component tree.
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
 * refreshes.  The hook exposes two surfaces:
 *   - Existing API (messages, sendMessage, clearMessages, isLoading) — used by
 *     ChatWindow, unchanged from before.
 *   - Session management API (sessions, activeSessionId, createSession, …) —
 *     used by Sidebar in Step 2.
 */
export function useChat() {
  const [sessions, setSessions] = useState<ChatSession[]>(readSessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    const stored = readSessions()
    return stored.length > 0 ? stored[0].id : null
  })

  // Keep a ref so callbacks that can't have sessions in their dep array can
  // still read the latest value without stale closures.
  const sessionsRef = useRef(sessions)
  useEffect(() => { sessionsRef.current = sessions }, [sessions])

  // Messages are derived — always the active session's messages or empty.
  const messages: ChatMessage[] =
    sessions.find((s) => s.id === activeSessionId)?.messages ?? []

  // ── Internal updater ───────────────────────────────────────────────────────

  const patchSessionMessages = useCallback(
    (sessionId: string, updater: (msgs: ChatMessage[]) => ChatMessage[]) => {
      setSessions((prev) => {
        const next = prev.map((s) =>
          s.id === sessionId
            ? { ...s, messages: updater(s.messages), updatedAt: new Date().toISOString() }
            : s
        )
        writeSessions(next)
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

  const mutation = useMutation({
    mutationFn: (payload: QueryRequest) => queryChat(payload),
  })

  const sendMessage = useCallback(
    async (question: string, documentId?: string) => {
      if (!question.trim()) return

      // Ensure there is an active session — auto-create one if needed.
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

      // Auto-title from the first user message (replaces the "New Chat" default).
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

      try {
        const { topK, threshold } = readQuerySettings()
        const res = await mutation.mutateAsync({
          question: question.trim(),
          top_k: topK,
          score_threshold: threshold,
        })

        patchSessionMessages(sessionId, (msgs) =>
          msgs.map((m) =>
            m.id === loadingId
              ? {
                  id: loadingId,
                  role: 'assistant',
                  content: res.answer,
                  citations: res.citations,
                  latency_ms: res.latency_ms,
                  isLoading: false,
                }
              : m
          )
        )
      } catch (err) {
        const errorText = err instanceof Error ? err.message : 'Something went wrong.'
        patchSessionMessages(sessionId, (msgs) =>
          msgs.map((m) =>
            m.id === loadingId
              ? { id: loadingId, role: 'assistant', content: errorText, isLoading: false, isError: true }
              : m
          )
        )
      }
    },
    [mutation, activeSessionId, patchSessionMessages]
  )

  const clearMessages = useCallback(() => {
    if (activeSessionId) patchSessionMessages(activeSessionId, () => [])
  }, [activeSessionId, patchSessionMessages])

  return {
    // ── Existing API — ChatWindow uses these; signature unchanged ──────────
    messages,
    sendMessage,
    clearMessages,
    isLoading: mutation.isPending,
    // ── Session management API — Sidebar will use these in Step 2 ─────────
    sessions,
    activeSessionId,
    createSession,
    loadSession,
    deleteSession,
    renameSession,
    searchSessions,
  }
}
