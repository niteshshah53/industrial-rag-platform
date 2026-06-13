import { useState } from 'react'
import { Plus, Search, X } from 'lucide-react'
import ChatHistoryList from './ChatHistoryList'
import SidebarDocumentSection from './SidebarDocumentSection'
import SidebarFooter from './SidebarFooter'
import type { ChatSession, DocumentRecord } from '../types'

interface Props {
  isOpen: boolean
  onClose: () => void
  sessions: ChatSession[]
  activeSessionId: string | null
  onNewChat: () => void
  onLoadSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onRenameSession: (id: string, title: string) => void
  selectedDocument: DocumentRecord | null
  onSelectDocument: (doc: DocumentRecord | null) => void
  onOpenSettings: () => void
  onOpenDocuments: () => void
}

export default function Sidebar({
  isOpen,
  onClose,
  sessions,
  activeSessionId,
  onNewChat,
  onLoadSession,
  onDeleteSession,
  onRenameSession,
  selectedDocument,
  onSelectDocument,
  onOpenSettings,
  onOpenDocuments,
}: Props) {
  const [searchQuery, setSearchQuery] = useState('')

  const filteredSessions = searchQuery.trim()
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions

  // On mobile the sidebar is a drawer — close it after the user navigates
  function closeOnMobile() {
    if (window.innerWidth < 1024) onClose()
  }

  return (
    <aside
      className={`
        fixed lg:relative inset-y-0 left-0 z-30
        w-64 shrink-0 flex flex-col bg-gray-900
        transform transition-transform duration-200 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}
    >
      {/* Logo + close (mobile only) */}
      <div className="flex items-center justify-between px-4 h-14 shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-indigo-600 flex items-center justify-center shrink-0">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="w-4 h-4 text-white"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span className="font-semibold text-white text-sm tracking-tight">DocIntel</span>
        </div>
        <button
          onClick={onClose}
          aria-label="Close sidebar"
          className="lg:hidden p-1 text-gray-400 hover:text-white rounded transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* New Chat button */}
      <div className="px-3 mb-3 shrink-0">
        <button
          onClick={() => { onNewChat(); closeOnMobile() }}
          title="New chat (Ctrl+Shift+O)"
          className="
            w-full flex items-center gap-2 px-3 py-2 rounded-lg
            bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium
            transition-colors active:scale-95
          "
        >
          <Plus size={16} />
          New Chat
          <span className="ml-auto text-[10px] font-mono opacity-50 hidden xl:block tracking-tight">
            ⌘⇧O
          </span>
        </button>
      </div>

      {/* Search */}
      <div className="px-3 mb-2 shrink-0">
        <div className="relative">
          <Search
            size={13}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
          />
          <input
            type="text"
            placeholder="Search conversations…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="
              w-full bg-gray-800 text-gray-200 placeholder-gray-500 text-xs
              rounded-lg pl-8 pr-7 py-1.5 border border-gray-700
              focus:outline-none focus:border-indigo-500 transition-colors
            "
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Chat history list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-1">
        <ChatHistoryList
          sessions={filteredSessions}
          activeSessionId={activeSessionId}
          onLoad={(id) => { onLoadSession(id); closeOnMobile() }}
          onDelete={onDeleteSession}
          onRename={onRenameSession}
        />
      </div>

      {/* Documents section */}
      <SidebarDocumentSection
        selectedDocument={selectedDocument}
        onSelectDocument={(doc) => { onSelectDocument(doc); closeOnMobile() }}
      />

      {/* Footer */}
      <SidebarFooter onOpenSettings={onOpenSettings} onOpenDocuments={onOpenDocuments} />
    </aside>
  )
}
