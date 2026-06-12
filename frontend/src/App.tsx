import { useState } from 'react'
import DocumentSidebar from './components/DocumentSidebar'
import ChatWindow from './components/ChatWindow'
import type { DocumentRecord } from './types'

export default function App() {
  const [selectedDoc, setSelectedDoc] = useState<DocumentRecord | null>(null)

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">
      {/* Top nav bar */}
      <header className="h-12 shrink-0 flex items-center px-5 bg-white border-b border-gray-200 shadow-sm z-10">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-indigo-600 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-white" stroke="currentColor" strokeWidth={2}>
              <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="font-semibold text-gray-900 text-sm tracking-tight">
            Industrial Document Intelligence
          </span>
        </div>
        <div className="ml-auto text-xs text-gray-400">
          Powered by Ollama · Qdrant · LangGraph
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        <DocumentSidebar selected={selectedDoc} onSelect={setSelectedDoc} />
        <ChatWindow selectedDocument={selectedDoc} />
      </div>
    </div>
  )
}
