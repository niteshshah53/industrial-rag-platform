import { useState } from 'react'
import {
  Loader2, AlertTriangle, Copy, Check, Trash2, RefreshCw,
  ThumbsUp, ThumbsDown, Pencil, Square,
} from 'lucide-react'
import CitationCard from './CitationCard'
import type { ChatMessage } from '../types'

interface Props {
  message: ChatMessage
  onDelete?: () => void
  onEdit?: () => void
  onRegenerate?: () => void
  onReaction?: (r: 'like' | 'dislike') => void
}

function ActionBtn({
  title,
  onClick,
  danger = false,
  active = false,
  children,
}: {
  title: string
  onClick: () => void
  danger?: boolean
  active?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`
        p-1.5 rounded-md transition-colors
        ${danger
          ? 'text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20'
          : active
            ? 'text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20'
            : 'text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
        }
      `}
    >
      {children}
    </button>
  )
}

export default function MessageBubble({ message, onDelete, onEdit, onRegenerate, onReaction }: Props) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    if (!message.content) return
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const isUser = message.role === 'user'
  const isDone = !message.isLoading && !message.isStreaming

  // ── User message ────────────────────────────────────────────────────────────

  if (isUser) {
    return (
      <div className="group flex flex-col items-end gap-1">
        {/* Action bar — hover-reveal on desktop, always on mobile */}
        {isDone && (
          <div className="flex items-center gap-0.5 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
            {onEdit && (
              <ActionBtn title="Edit message" onClick={onEdit}>
                <Pencil size={13} />
              </ActionBtn>
            )}
            <ActionBtn title={copied ? 'Copied!' : 'Copy'} onClick={handleCopy} active={copied}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </ActionBtn>
            {onDelete && (
              <ActionBtn title="Delete message" onClick={onDelete} danger>
                <Trash2 size={13} />
              </ActionBtn>
            )}
          </div>
        )}
        <div className="max-w-[82%] lg:max-w-[72%] bg-indigo-600 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    )
  }

  // ── Error message ────────────────────────────────────────────────────────────

  if (message.isError) {
    return (
      <div className="group flex flex-col gap-1">
        <div className="
          bg-red-50 dark:bg-red-900/20
          border border-red-200 dark:border-red-800
          text-red-700 dark:text-red-400
          px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed
          flex items-start gap-2.5
          max-w-[90%]
        ">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        {isDone && onDelete && (
          <div className="flex items-center gap-0.5 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
            {onRegenerate && (
              <ActionBtn title="Retry" onClick={onRegenerate}>
                <RefreshCw size={13} />
              </ActionBtn>
            )}
            <ActionBtn title="Delete message" onClick={onDelete} danger>
              <Trash2 size={13} />
            </ActionBtn>
          </div>
        )}
      </div>
    )
  }

  // ── Assistant message ────────────────────────────────────────────────────────

  const sourceCount = message.citations?.length ?? 0
  const latencyS = message.latency_ms !== undefined
    ? (message.latency_ms / 1000).toFixed(1)
    : null

  return (
    <div className="group flex flex-col gap-1">
      {/* Content area */}
      <div className="text-sm leading-relaxed text-gray-900 dark:text-gray-100">
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

      {/* Citations */}
      {isDone && message.citations && message.citations.length > 0 && (
        <CitationCard citations={message.citations} />
      )}

      {/* Metadata + actions row */}
      <div className="flex items-center gap-2 min-h-[24px]">
        {/* Subtle metadata — only when response is complete */}
        {isDone && (latencyS || sourceCount > 0 || message.isStopped) && (
          <span className="text-xs text-gray-400 dark:text-gray-500 select-none">
            {message.isStopped && (
              <span className="inline-flex items-center gap-1 mr-2">
                <Square size={9} className="fill-current" />
                Stopped
              </span>
            )}
            {latencyS && `${latencyS}s`}
            {latencyS && sourceCount > 0 && ' · '}
            {sourceCount > 0 && `${sourceCount} source${sourceCount > 1 ? 's' : ''}`}
          </span>
        )}

        {/* Action bar — hover-reveal on desktop */}
        {isDone && !message.isLoading && (
          <div className="flex items-center gap-0.5 opacity-100 lg:opacity-0 lg:group-hover:opacity-100 transition-opacity">
            <ActionBtn title={copied ? 'Copied!' : 'Copy'} onClick={handleCopy} active={copied}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </ActionBtn>
            {onRegenerate && (
              <ActionBtn title="Regenerate response" onClick={onRegenerate}>
                <RefreshCw size={13} />
              </ActionBtn>
            )}
            {onReaction && (
              <>
                <ActionBtn
                  title="Good response"
                  onClick={() => onReaction('like')}
                  active={message.reaction === 'like'}
                >
                  <ThumbsUp size={13} />
                </ActionBtn>
                <ActionBtn
                  title="Bad response"
                  onClick={() => onReaction('dislike')}
                  active={message.reaction === 'dislike'}
                >
                  <ThumbsDown size={13} />
                </ActionBtn>
              </>
            )}
            {onDelete && (
              <ActionBtn title="Delete message" onClick={onDelete} danger>
                <Trash2 size={13} />
              </ActionBtn>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
