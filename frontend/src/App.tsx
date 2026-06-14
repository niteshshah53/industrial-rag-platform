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

  const {
    messages,
    sendMessage,
    isLoading,
    sessions,
    activeSessionId,
    createSession,
    loadSession,
    deleteSession,
    renameSession,
  } = useChat()

  const handleNewChat = useCallback(() => {
    createSession(selectedDoc?.document_id)
  }, [createSession, selectedDoc])

  const chatEnabled = (selectedDoc && selectedDoc.status === 'READY') || selectedCollection !== null

  // Global keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey
      // Cmd/Ctrl+B — toggle sidebar (mobile drawer)
      if (meta && !e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        setSidebarOpen((prev) => !prev)
      }
      // Cmd/Ctrl+Shift+O — new chat
      if (meta && e.shiftKey && e.key.toLowerCase() === 'o') {
        e.preventDefault()
        handleNewChat()
      }
      // Escape — close settings panel
      if (e.key === 'Escape' && settingsOpen) {
        setSettingsOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [handleNewChat, settingsOpen])

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
        selectedDocument={selectedDoc}
        onSelectDocument={(doc) => { setSelectedDoc(doc); if (doc) setSelectedCollection(null) }}
        selectedCollection={selectedCollection}
        onSelectCollection={(col) => { setSelectedCollection(col); if (col) setSelectedDoc(null) }}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenDocuments={() => setDocumentsOpen(true)}
        onOpenCollections={() => setCollectionsOpen(true)}
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
            {/* Primary: active session title (or app name as fallback) */}
            <p className="font-semibold text-gray-800 dark:text-gray-100 text-sm truncate leading-tight">
              {sessions.find((s) => s.id === activeSessionId)?.title ?? 'Industrial Document Intelligence'}
            </p>
            {/* Subtitle: selected document or collection name */}
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
          messages={messages}
          onSuggestPrompt={setSuggestedInput}
        />

        <ChatInputBar
          disabled={!chatEnabled}
          isLoading={isLoading}
          onSend={(text) => sendMessage(text, selectedDoc?.document_id, selectedCollection?.collection_id)}
          onDocumentUploaded={(doc) => { setSelectedDoc(doc); setSelectedCollection(null) }}
          suggestedInput={suggestedInput}
          onSuggestConsumed={() => setSuggestedInput('')}
        />
      </div>
    </div>
  )
}
