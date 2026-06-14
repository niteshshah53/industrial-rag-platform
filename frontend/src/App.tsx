import { useState, useCallback, useEffect } from 'react'
import { Menu } from 'lucide-react'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import ChatInputBar from './components/ChatInputBar'
import SettingsPanel from './components/SettingsPanel'
import DocumentsPanel from './components/DocumentsPanel'
import CollectionsPanel from './components/CollectionsPanel'
import { useChat } from './hooks/useChat'
import { useTheme } from './hooks/useTheme'
import type { Collection, DocumentRecord } from './types'

export default function App() {
  useTheme()

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null)
  const [selectedCollection, setSelectedCollection] = useState<Collection | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [documentsOpen, setDocumentsOpen] = useState(false)
  const [collectionsOpen, setCollectionsOpen] = useState(false)
  const [suggestedInput, setSuggestedInput] = useState('')
  const [focusSearchSignal, setFocusSearchSignal] = useState(0)

  const {
    messages,
    sendMessage,
    stopGeneration,
    isLoading,
    sessions,
    activeSessionId,
    createSession,
    loadSession,
    deleteSession,
    renameSession,
    pinSession,
    archiveSession,
    deleteMessage,
    truncateFrom,
    reactToMessage,
  } = useChat()

  const handleNewChat = useCallback(() => {
    createSession(selectedDoc?.document_id)
  }, [createSession, selectedDoc])

  const chatEnabled = (selectedDoc && selectedDoc.status === 'READY') || selectedCollection !== null

  // ── Message actions ────────────────────────────────────────────────────────

  function handleRegenerate(assistantMsgId: string) {
    const session = sessions.find((s) => s.id === activeSessionId)
    if (!session) return
    const idx = session.messages.findIndex((m) => m.id === assistantMsgId)
    if (idx <= 0) return
    const prevUser = session.messages[idx - 1]
    if (prevUser.role !== 'user') return
    truncateFrom(assistantMsgId)
    sendMessage(prevUser.content, selectedDoc?.document_id, selectedCollection?.collection_id)
  }

  function handleEditUserMessage(msgId: string, content: string) {
    truncateFrom(msgId)
    setSuggestedInput(content)
  }

  // ── Global keyboard shortcuts ──────────────────────────────────────────────

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey

      if (meta && !e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        setSidebarOpen((prev) => !prev)
        return
      }

      if (meta && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault()
        handleNewChat()
        return
      }

      // Cmd/Ctrl+K — focus sidebar search
      if (meta && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSidebarOpen(true)
        setFocusSearchSignal((s) => s + 1)
        return
      }

      // Cmd/Ctrl+Shift+C — copy last assistant message
      if (meta && e.shiftKey && e.key.toLowerCase() === 'c') {
        const tag = (e.target as HTMLElement).tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA') return // don't hijack text copy
        e.preventDefault()
        const session = sessions.find((s) => s.id === activeSessionId)
        if (!session) return
        const last = [...session.messages].reverse().find(
          (m) => m.role === 'assistant' && !m.isLoading && !m.isStreaming && m.content
        )
        if (last) navigator.clipboard.writeText(last.content)
        return
      }

      // Cmd/Ctrl+Shift+R — regenerate last assistant response
      if (meta && e.shiftKey && e.key.toLowerCase() === 'r') {
        e.preventDefault()
        if (isLoading) return
        const session = sessions.find((s) => s.id === activeSessionId)
        if (!session) return
        const last = [...session.messages].reverse().find(
          (m) => m.role === 'assistant' && !m.isLoading && !m.isStreaming
        )
        if (last) handleRegenerate(last.id)
        return
      }

      // Escape — stop generation first, then close panels
      if (e.key === 'Escape') {
        if (isLoading) {
          stopGeneration()
          return
        }
        if (settingsOpen) { setSettingsOpen(false); return }
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [handleNewChat, settingsOpen, sessions, activeSessionId, isLoading, stopGeneration]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-900 transition-colors duration-200">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewChat={handleNewChat}
        onLoadSession={loadSession}
        onDeleteSession={deleteSession}
        onRenameSession={renameSession}
        onPinSession={pinSession}
        onArchiveSession={archiveSession}
        selectedDocument={selectedDoc}
        onSelectDocument={(doc) => { setSelectedDoc(doc); if (doc) setSelectedCollection(null) }}
        selectedCollection={selectedCollection}
        onSelectCollection={(col) => { setSelectedCollection(col); if (col) setSelectedDoc(null) }}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenDocuments={() => setDocumentsOpen(true)}
        onOpenCollections={() => setCollectionsOpen(true)}
        focusSearchSignal={focusSearchSignal}
      />

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />

      <DocumentsPanel
        isOpen={documentsOpen}
        onClose={() => setDocumentsOpen(false)}
        selectedDocumentId={selectedDoc?.document_id ?? null}
        onDocumentDeleted={(ids) => {
          if (selectedDoc && ids.includes(selectedDoc.document_id)) {
            setSelectedDoc(null)
          }
        }}
      />

      <CollectionsPanel
        isOpen={collectionsOpen}
        onClose={() => setCollectionsOpen(false)}
        selectedCollectionId={selectedCollection?.collection_id ?? null}
        onCollectionDeleted={(id) => {
          if (selectedCollection?.collection_id === id) {
            setSelectedCollection(null)
          }
        }}
      />

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Mobile topbar */}
        <div className="lg:hidden flex items-center px-4 h-12 shrink-0 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 gap-3">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            title="Open sidebar (Ctrl+B)"
            className="shrink-0 p-1 text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 rounded transition-colors"
          >
            <Menu size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-gray-800 dark:text-gray-100 text-sm truncate leading-tight">
              {sessions.find((s) => s.id === activeSessionId)?.title ?? 'Industrial Document Intelligence'}
            </p>
            {selectedDoc && (
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate leading-tight">
                {selectedDoc.filename}
              </p>
            )}
            {selectedCollection && !selectedDoc && (
              <p className="text-xs text-gray-400 dark:text-gray-500 truncate leading-tight">
                {selectedCollection.name} ({selectedCollection.document_ids.length} docs)
              </p>
            )}
          </div>
        </div>

        <ChatWindow
          selectedDocument={selectedDoc}
          selectedCollection={selectedCollection}
          messages={messages}
          isLoading={isLoading}
          onSuggestPrompt={setSuggestedInput}
          onDeleteMessage={deleteMessage}
          onReactToMessage={reactToMessage}
          onRegenerate={handleRegenerate}
          onEditUserMessage={handleEditUserMessage}
        />

        <ChatInputBar
          disabled={!chatEnabled}
          isLoading={isLoading}
          onSend={(text) => sendMessage(text, selectedDoc?.document_id, selectedCollection?.collection_id)}
          onStop={stopGeneration}
          onDocumentUploaded={(doc) => { setSelectedDoc(doc); setSelectedCollection(null) }}
          suggestedInput={suggestedInput}
          onSuggestConsumed={() => setSuggestedInput('')}
        />
      </div>
    </div>
  )
}
