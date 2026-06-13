import { useState } from 'react'
import { FileText, ChevronDown, RefreshCw, AlertCircle } from 'lucide-react'
import { useDocuments } from '../hooks/useDocuments'
import type { DocumentRecord, DocumentStatus } from '../types'

const statusDot: Record<DocumentStatus, string> = {
  ready: 'bg-green-500',
  processing: 'bg-blue-400 animate-pulse',
  pending: 'bg-yellow-400',
  failed: 'bg-red-500',
}

interface Props {
  selectedDocument: DocumentRecord | null
  onSelectDocument: (doc: DocumentRecord | null) => void
}

export default function SidebarDocumentSection({ selectedDocument, onSelectDocument }: Props) {
  const [expanded, setExpanded] = useState(true)
  const { data: docs, isLoading, isError, refetch } = useDocuments()

  return (
    <div className="shrink-0 border-t border-gray-700 px-2 py-2">
      {/* Section header */}
      <div className="flex items-center justify-between px-1 mb-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-gray-200 transition-colors"
        >
          <ChevronDown
            size={13}
            className={`transition-transform duration-150 ${expanded ? '' : '-rotate-90'}`}
          />
          Documents
        </button>
        <button
          onClick={() => refetch()}
          title="Refresh"
          className="text-gray-500 hover:text-gray-300 transition-colors"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      {expanded && (
        <div className="space-y-0.5 max-h-40 overflow-y-auto scrollbar-thin">
          {/* Loading skeleton */}
          {isLoading && (
            <div className="space-y-1.5 px-1 py-1">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-7 rounded-md bg-gray-800 animate-pulse" />
              ))}
            </div>
          )}

          {/* Network error */}
          {isError && !isLoading && (
            <div className="flex items-center gap-1.5 px-2 py-2">
              <AlertCircle size={12} className="text-red-400 shrink-0" />
              <span className="text-xs text-red-400">Failed to load.</span>
              <button
                onClick={() => refetch()}
                className="text-xs text-indigo-400 hover:text-indigo-300 underline ml-auto"
              >
                Retry
              </button>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && !isError && docs && docs.length === 0 && (
            <p className="text-xs text-gray-500 px-2 py-2 text-center">
              No documents yet — use + to upload.
            </p>
          )}

          {/* Document list */}
          {docs?.map((doc) => {
            const isSelected = selectedDocument?.document_id === doc.document_id
            const isReady = doc.status === 'ready'
            return (
              <button
                key={doc.document_id}
                onClick={() => isReady && onSelectDocument(isSelected ? null : doc)}
                disabled={!isReady}
                title={doc.filename}
                className={`
                  w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs
                  transition-colors text-left
                  ${isSelected ? 'bg-indigo-600 text-white' : 'text-gray-300 hover:bg-gray-800'}
                  ${!isReady ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                `}
              >
                <FileText size={12} className="shrink-0" />
                <span className="flex-1 truncate">{doc.filename}</span>
                <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${statusDot[doc.status]}`} />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
