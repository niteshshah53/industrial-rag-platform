import { useState, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import { queryChat } from '../api/client'
import type { ChatMessage, QueryRequest } from '../types'

let msgCounter = 0
function nextId() {
  return `msg-${++msgCounter}`
}

/**
 * Manages the chat message history and exposes sendMessage.
 *
 * @param scoreThreshold  Cosine similarity threshold forwarded to the backend.
 */
export function useChat(scoreThreshold = 0.5) {
  const [messages, setMessages] = useState<ChatMessage[]>([])

  const mutation = useMutation({
    mutationFn: (payload: QueryRequest) => queryChat(payload),
  })

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim()) return

      // 1. Add user message immediately
      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: question.trim(),
      }

      // 2. Add a loading placeholder for the assistant
      const loadingId = nextId()
      const loadingMsg: ChatMessage = {
        id: loadingId,
        role: 'assistant',
        content: '',
        isLoading: true,
      }

      setMessages((prev) => [...prev, userMsg, loadingMsg])

      try {
        const res = await mutation.mutateAsync({
          question: question.trim(),
          top_k: 5,
          score_threshold: scoreThreshold,
        })

        // 3. Replace loading placeholder with real answer
        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingId
              ? {
                  id: loadingId,
                  role: 'assistant',
                  content: res.answer,
                  citations: res.citations,
                  latency_ms: res.latency_ms,
                  isLoading: false,
                }
              : m,
          ),
        )
      } catch (err) {
        const errorText =
          err instanceof Error ? err.message : 'Something went wrong.'

        setMessages((prev) =>
          prev.map((m) =>
            m.id === loadingId
              ? {
                  id: loadingId,
                  role: 'assistant',
                  content: `Error: ${errorText}`,
                  isLoading: false,
                }
              : m,
          ),
        )
      }
    },
    [mutation, scoreThreshold],
  )

  const clearMessages = useCallback(() => setMessages([]), [])

  return { messages, sendMessage, clearMessages, isLoading: mutation.isPending }
}
