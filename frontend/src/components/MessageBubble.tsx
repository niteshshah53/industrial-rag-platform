import { Loader2, AlertTriangle } from 'lucide-react'
import CitationCard from './CitationCard'
import type { ChatMessage } from '../types'

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-indigo-600 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  // Error message — shown when the RAG query or network call fails
  if (message.isError) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[80%]">
          <div className="
            bg-red-50 dark:bg-red-900/20
            border border-red-200 dark:border-red-800
            text-red-700 dark:text-red-400
            px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed
            flex items-start gap-2.5
          ">
            <AlertTriangle size={15} className="shrink-0 mt-0.5" />
            <p className="whitespace-pre-wrap">{message.content}</p>
          </div>
        </div>
      </div>
    )
  }

  // Normal assistant message
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%]">
        <div className="bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed">
          {message.isLoading ? (
            <span className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
              <Loader2 size={14} className="animate-spin" />
              Thinking…
            </span>
          ) : message.isStreaming ? (
            <p className="whitespace-pre-wrap">
              {message.content}
              <span className="inline-block w-0.5 h-[1em] bg-gray-500 dark:bg-gray-400 ml-0.5 align-middle animate-pulse" />
            </p>
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>

        {!message.isLoading && message.citations && message.citations.length > 0 && (
          <CitationCard citations={message.citations} />
        )}

        {!message.isLoading && message.latency_ms !== undefined && (
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 px-1">
            {(message.latency_ms / 1000).toFixed(1)} s
          </p>
        )}
      </div>
    </div>
  )
}
