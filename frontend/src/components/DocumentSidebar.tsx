import type { MouseEvent } from 'react'
import { Trash2, FileText, RefreshCw } from 'lucide-react'
import StatusBadge from './StatusBadge'
import UploadDropzone from './UploadDropzone'
import { useDocuments, useDeleteDocument } from '../hooks/useDocuments'
import type { DocumentRecord } from '../types'

interface Props {
  selected: DocumentRecord | null
  onSelect: (doc: DocumentRecord | null) => void
}

export default function DocumentSidebar({ selected, onSelect }: Props) {
  const { data: docs, isLoading, isError, refetch } = useDocuments()
  const { mutate: remove, isPending: isDeleting } = useDeleteDocument()

  function handleDelete(e: MouseEvent, doc: DocumentRecord) {
    e.stopPropagation()
    if (!confirm(`Delete "${doc.filename}"?`)) return
    remove(doc.document_id, {
      onSuccess: () => {
        if (selected?.document_id === doc.document_id) onSelect(null)
      },
    })
  }

  return (
    <aside className="w-72 shrink-0 flex flex-col border-r border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="font-semibold text-gray-800 text-sm">Documents</h2>
        <button
          onClick={() => refetch()}
          title="Refresh"
          className="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Upload zone */}
      <div className="pt-3">
        <UploadDropzone />
      </div>

      {/* Document list */}
      <nav className="flex-1 overflow-y-auto scrollbar-thin">
        {isLoading && (
          <p className="px-4 py-6 text-sm text-gray-400 text-center">Loading…</p>
        )}
        {isError && (
          <p className="px-4 py-6 text-sm text-red-500 text-center">Failed to load documents.</p>
        )}
        {docs && docs.length === 0 && (
          <p className="px-4 py-6 text-sm text-gray-400 text-center">
            No documents yet. Upload one above.
          </p>
        )}
        {docs && docs.map((doc) => {
          const isSelected = selected?.document_id === doc.document_id
          return (
            <button
              key={doc.document_id}
              onClick={() => onSelect(isSelected ? null : doc)}
              disabled={doc.status !== 'ready'}
              className={`
                w-full text-left px-4 py-3 flex items-start gap-3 border-b border-gray-100
                transition-colors group
                ${isSelected ? 'bg-indigo-50' : 'hover:bg-gray-50'}
                ${doc.status !== 'ready' ? 'opacity-60 cursor-default' : 'cursor-pointer'}
              `}
            >
              <FileText
                size={16}
                className={`shrink-0 mt-0.5 ${isSelected ? 'text-indigo-600' : 'text-gray-400'}`}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{doc.filename}</p>
                <div className="flex items-center justify-between mt-1">
                  <StatusBadge status={doc.status} />
                  {doc.chunk_count !== null && (
                    <span className="text-xs text-gray-400">{doc.chunk_count} chunks</span>
                  )}
                </div>
              </div>
              {(doc.status === 'ready' || doc.status === 'failed') && (
                <button
                  onClick={(e) => handleDelete(e, doc)}
                  disabled={isDeleting}
                  title="Delete document"
                  className="opacity-0 group-hover:opacity-100 shrink-0 text-gray-400 hover:text-red-500 transition-all"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
