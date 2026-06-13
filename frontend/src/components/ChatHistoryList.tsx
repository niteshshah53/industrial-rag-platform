import ChatHistoryItem from './ChatHistoryItem'
import type { ChatSession } from '../types'

interface Props {
  sessions: ChatSession[]
  activeSessionId: string | null
  onLoad: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
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

export default function ChatHistoryList({ sessions, activeSessionId, onLoad, onDelete, onRename }: Props) {
  if (sessions.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-xs text-gray-500">No conversations yet.</p>
        <p className="text-xs text-gray-600 mt-1">Start a new chat above.</p>
      </div>
    )
  }

  const groups = groupByDate(sessions)

  return (
    <div className="space-y-4 pb-2">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-2 mb-1 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            {group.label}
          </p>
          <div className="space-y-0.5">
            {group.items.map((session) => (
              <ChatHistoryItem
                key={session.id}
                session={session}
                isActive={session.id === activeSessionId}
                onLoad={() => onLoad(session.id)}
                onDelete={() => onDelete(session.id)}
                onRename={(title) => onRename(session.id, title)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
