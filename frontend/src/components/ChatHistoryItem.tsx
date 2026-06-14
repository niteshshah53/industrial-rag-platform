import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Pencil, Trash2, Check, X, Pin, Archive } from 'lucide-react'
import type { ChatSession } from '../types'

interface Props {
  session: ChatSession
  isActive: boolean
  onLoad: () => void
  onDelete: () => void
  onRename: (title: string) => void
  onPin?: () => void
  onArchive?: () => void
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 30) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString()
}

export default function ChatHistoryItem({
  session,
  isActive,
  onLoad,
  onDelete,
  onRename,
  onPin,
  onArchive,
}: Props) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState(session.title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isRenaming) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [isRenaming])

  function commitRename() {
    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== session.title) onRename(trimmed)
    setIsRenaming(false)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') { e.preventDefault(); commitRename() }
    if (e.key === 'Escape') { setIsRenaming(false); setRenameValue(session.title) }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !isRenaming && onLoad()}
      onKeyDown={(e) => e.key === 'Enter' && !isRenaming && onLoad()}
      className={`
        group relative flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer
        transition-colors text-sm select-none outline-none
        focus-visible:ring-1 focus-visible:ring-indigo-500
        ${isActive ? 'bg-gray-700 text-white' : 'text-gray-300 hover:bg-gray-800'}
      `}
    >
      {isRenaming ? (
        <div className="flex-1 flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <input
            ref={inputRef}
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={commitRename}
            className="flex-1 min-w-0 bg-gray-600 text-white text-xs rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          />
          <button
            onClick={(e) => { e.stopPropagation(); commitRename() }}
            className="shrink-0 p-0.5 text-green-400 hover:text-green-300"
          >
            <Check size={13} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setIsRenaming(false); setRenameValue(session.title) }}
            className="shrink-0 p-0.5 text-gray-400 hover:text-gray-200"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1 min-w-0">
              {session.isPinned && (
                <Pin size={10} className="shrink-0 text-indigo-400 fill-current" />
              )}
              <p className="truncate text-sm leading-5">{session.title}</p>
            </div>
            <p className="text-xs text-gray-500 leading-4">{timeAgo(session.updatedAt)}</p>
          </div>

          {/* Action buttons */}
          <div
            className="flex lg:hidden lg:group-hover:flex items-center gap-0.5 shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => { setRenameValue(session.title); setIsRenaming(true) }}
              title="Rename"
              className="p-2 lg:p-1 text-gray-400 hover:text-gray-100 rounded transition-colors"
            >
              <Pencil size={12} />
            </button>
            {onPin && (
              <button
                onClick={onPin}
                title={session.isPinned ? 'Unpin' : 'Pin to top'}
                className={`p-2 lg:p-1 rounded transition-colors ${
                  session.isPinned
                    ? 'text-indigo-400 hover:text-indigo-300'
                    : 'text-gray-400 hover:text-indigo-400'
                }`}
              >
                <Pin size={12} className={session.isPinned ? 'fill-current' : ''} />
              </button>
            )}
            {onArchive && (
              <button
                onClick={onArchive}
                title="Archive"
                className="p-2 lg:p-1 text-gray-400 hover:text-yellow-400 rounded transition-colors"
              >
                <Archive size={12} />
              </button>
            )}
            <button
              onClick={() => { if (confirm(`Delete "${session.title}"?`)) onDelete() }}
              title="Delete"
              className="p-2 lg:p-1 text-gray-400 hover:text-red-400 rounded transition-colors"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
