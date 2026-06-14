import { useState } from 'react'
import { Archive } from 'lucide-react'
import ChatHistoryItem from './ChatHistoryItem'
import type { ChatSession } from '../types'

interface Props {
  sessions: ChatSession[]
  activeSessionId: string | null
  onLoad: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onPin?: (id: string) => void
  onArchive?: (id: string) => void
}

interface Group {
  label: string
  items: ChatSession[]
}

function groupByDate(sessions: ChatSession[]): Group[] {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const lastWeek = new Date(today); lastWeek.setDate(today.getDate() - 7)

  const groups: Group[] = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Last 7 Days', items: [] },
    { label: 'Older', items: [] },
  ]

  for (const session of sessions) {
    const d = new Date(session.updatedAt)
    if (d >= today) groups[0].items.push(session)
    else if (d >= yesterday) groups[1].items.push(session)
    else if (d >= lastWeek) groups[2].items.push(session)
    else groups[3].items.push(session)
  }

  return groups.filter((g) => g.items.length > 0)
}

export default function ChatHistoryList({
  sessions,
  activeSessionId,
  onLoad,
  onDelete,
  onRename,
  onPin,
  onArchive,
}: Props) {
  const [showArchived, setShowArchived] = useState(false)

  const pinned = sessions.filter((s) => s.isPinned && !s.isArchived)
  const regular = sessions.filter((s) => !s.isPinned && !s.isArchived)
  const archived = sessions.filter((s) => s.isArchived)

  const hasAny = pinned.length + regular.length + archived.length > 0

  if (!hasAny) {
    return (
      <div className="py-8 text-center">
        <p className="text-xs text-gray-500">No conversations yet.</p>
        <p className="text-xs text-gray-600 mt-1">Start a new chat above.</p>
      </div>
    )
  }

  const regularGroups = groupByDate(regular)

  function itemProps(session: ChatSession) {
    return {
      session,
      isActive: session.id === activeSessionId,
      onLoad: () => onLoad(session.id),
      onDelete: () => onDelete(session.id),
      onRename: (title: string) => onRename(session.id, title),
      onPin: onPin ? () => onPin(session.id) : undefined,
      onArchive: onArchive ? () => onArchive(session.id) : undefined,
    }
  }

  return (
    <div className="space-y-4 pb-2">
      {/* Pinned section */}
      {pinned.length > 0 && (
        <div>
          <p className="px-2 mb-1 text-xs font-semibold text-indigo-400 uppercase tracking-wider">
            Pinned
          </p>
          <div className="space-y-0.5">
            {pinned.map((session) => (
              <ChatHistoryItem key={session.id} {...itemProps(session)} />
            ))}
          </div>
        </div>
      )}

      {/* Regular sessions grouped by date */}
      {regularGroups.map((group) => (
        <div key={group.label}>
          <p className="px-2 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            {group.label}
          </p>
          <div className="space-y-0.5">
            {group.items.map((session) => (
              <ChatHistoryItem key={session.id} {...itemProps(session)} />
            ))}
          </div>
        </div>
      ))}

      {/* Archived sessions */}
      {archived.length > 0 && (
        <div>
          <button
            onClick={() => setShowArchived((v) => !v)}
            className="w-full flex items-center gap-2 px-2 py-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            <Archive size={12} />
            {showArchived ? 'Hide' : 'Show'} {archived.length} archived
          </button>
          {showArchived && (
            <div className="space-y-0.5 mt-1 border-t border-gray-700 pt-2">
              {archived.map((session) => (
                <ChatHistoryItem key={session.id} {...itemProps(session)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
