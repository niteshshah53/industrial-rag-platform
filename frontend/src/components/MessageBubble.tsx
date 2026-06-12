import { Loader2 } from 'lucide-react'
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

  // Assistant message
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%]">
        <div className="bg-gray-100 text-gray-900 px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed">
          {message.isLoading ? (
            <span className="flex items-center gap-2 text-gray-500">
              <Loader2 size={14} className="animate-spin" />
              Thinking…
            </span>
          ) : (
            <p className="whitespace-pre-wrap">{message.content}</p>
          )}
        </div>

        {!message.isLoading && message.citations && message.citations.length > 0 && (
          <CitationCard citations={message.citations} />
        )}

        {!message.isLoading && message.latency_ms !== undefined && (
          <p className="mt-1 text-xs text-gray-400 px-1">
            {(message.latency_ms / 1000).toFixed(1)} s
          </p>
        )}
      </div>
    </div>
  )
}
