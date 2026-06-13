import { useState } from 'react'
import { X, Trash2, FileText, AlertTriangle, Loader2, Files } from 'lucide-react'
import { useDocuments, useBulkDeleteDocuments } from '../hooks/useDocuments'
import type { DocumentStatus } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1_024) return `${bytes} B`
  if (bytes < 1_048_576) return `${(bytes / 1_024).toFixed(1)} KB`
  return `${(bytes / 1_048_576).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

const STATUS_CFG: Record<DocumentStatus, { dot: string; label: string; text: string }> = {
  ready:      { dot: 'bg-green-500',               label: 'Ready',      text: 'text-green-600 dark:text-green-400' },
  processing: { dot: 'bg-blue-400 animate-pulse',  label: 'Processing', text: 'text-blue-500 dark:text-blue-400' },
  pending:    { dot: 'bg-yellow-400',              label: 'Pending',    text: 'text-yellow-600 dark:text-yellow-400' },
  failed:     { dot: 'bg-red-500',                label: 'Failed',     text: 'text-red-500' },
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen: boolean
  onClose: () => void
  /** document_id of the currently active document, for the "Active" badge */
  selectedDocumentId: string | null
  /** Called with the list of IDs that were just deleted, so App can deselect */
  onDocumentDeleted: (ids: string[]) => void
}

export default function DocumentsPanel({
  isOpen,
  onClose,
  selectedDocumentId,
  onDocumentDeleted,
}: Props) {
  const { data: docs = [], isLoading } = useDocuments()
  const { mutateAsync: bulkDelete, isPending: isDeleting } = useBulkDeleteDocuments()

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null)

  // ── Selection helpers ──────────────────────────────────────────────────────

  const allChecked = docs.length > 0 && docs.every((d) => selectedIds.has(d.document_id))
  const someChecked = selectedIds.size > 0 && !allChecked

  function toggleAll() {
    if (allChecked || someChecked) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(docs.map((d) => d.document_id)))
    }
  }

  function toggleOne(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ── Deletion flow ──────────────────────────────────────────────────────────

  function requestDelete(ids: string[]) {
    setPendingDelete(ids)
  }

  async function confirmDelete() {
    if (!pendingDelete) return
    try {
      await bulkDelete(pendingDelete)
      onDocumentDeleted(pendingDelete)
      setSelectedIds((prev) => {
        const next = new Set(prev)
        pendingDelete.forEach((id) => next.delete(id))
        return next
      })
    } finally {
      setPendingDelete(null)
    }
  }

  const pendingName =
    pendingDelete?.length === 1
      ? `"${docs.find((d) => d.document_id === pendingDelete[0])?.filename ?? 'this document'}"`
      : `${pendingDelete?.length ?? 0} documents`

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Backdrop */}
      <div
        className={`
          fixed inset-0 bg-black/40 z-40
          transition-opacity duration-200
          ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}
        `}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-in panel (from the right) */}
      <div
        role="dialog"
        aria-label="Document management"
        aria-modal="true"
        className={`
          fixed inset-y-0 right-0 z-50
          w-full sm:w-[460px]
          bg-white dark:bg-gray-900
          border-l border-gray-200 dark:border-gray-700
          flex flex-col shadow-2xl
          transform transition-transform duration-200 ease-in-out
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <div className="flex items-center gap-2.5">
            <Files size={18} className="text-indigo-600 shrink-0" />
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Documents</h2>
              {!isLoading && (
                <p className="text-xs text-gray-400 leading-tight">
                  {docs.length === 0
                    ? 'No documents uploaded yet'
                    : `${docs.length} document${docs.length !== 1 ? 's' : ''} in knowledge base`}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close documents panel"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Bulk action bar — visible when items are selected */}
        {selectedIds.size > 0 && !pendingDelete && (
          <div className="flex items-center justify-between px-5 py-2.5 bg-indigo-50 dark:bg-indigo-900/20 border-b border-indigo-200 dark:border-indigo-800 shrink-0">
            <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">
              {selectedIds.size} selected
            </span>
            <button
              onClick={() => requestDelete(Array.from(selectedIds))}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-medium transition-colors"
            >
              <Trash2 size={12} />
              Delete selected
            </button>
          </div>
        )}

        {/* Select-all bar */}
        {docs.length > 0 && !pendingDelete && (
          <div className="flex items-center px-5 py-2 border-b border-gray-100 dark:border-gray-800 shrink-0">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={allChecked}
                ref={(el) => { if (el) el.indeterminate = someChecked }}
                onChange={toggleAll}
                className="w-4 h-4 rounded accent-indigo-600 cursor-pointer"
              />
              <span className="text-xs text-gray-500 dark:text-gray-400">Select all</span>
            </label>
          </div>
        )}

        {/* Document list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={24} className="animate-spin text-indigo-600" />
            </div>
          )}

          {!isLoading && docs.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <FileText size={40} className="text-gray-200 dark:text-gray-700 mb-3" />
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                No documents yet
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                Upload a document using the + button in the chat.
              </p>
            </div>
          )}

          {docs.map((doc) => {
            const cfg = STATUS_CFG[doc.status]
            const isChecked = selectedIds.has(doc.document_id)
            const isActive = doc.document_id === selectedDocumentId

            return (
              <div
                key={doc.document_id}
                className={`
                  flex items-center gap-3 px-5 py-3.5
                  border-b border-gray-100 dark:border-gray-800
                  group transition-colors
                  ${isActive
                    ? 'bg-indigo-50/60 dark:bg-indigo-900/10'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'}
                `}
              >
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggleOne(doc.document_id)}
                  className="w-4 h-4 rounded accent-indigo-600 cursor-pointer shrink-0"
                />

                {/* File icon */}
                <div className="shrink-0 w-9 h-9 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                  <FileText size={17} className="text-indigo-600" />
                </div>

                {/* Metadata */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                      {doc.filename}
                    </p>
                    {isActive && (
                      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded">
                        Active
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                    <span className="text-xs text-gray-400">{formatBytes(doc.file_size_bytes)}</span>
                    <span className="text-gray-300 dark:text-gray-700 text-xs">·</span>
                    <span className="text-xs text-gray-400">{formatDate(doc.upload_timestamp)}</span>
                    <span className="text-gray-300 dark:text-gray-700 text-xs">·</span>
                    <span className={`flex items-center gap-1 text-xs font-medium ${cfg.text}`}>
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
                      {cfg.label}
                      {doc.status === 'ready' && doc.chunk_count > 0 && (
                        <span className="text-gray-400 font-normal ml-0.5">
                          ({doc.chunk_count} chunks)
                        </span>
                      )}
                    </span>
                  </div>
                </div>

                {/* Per-row delete button — revealed on hover */}
                <button
                  onClick={() => requestDelete([doc.document_id])}
                  title="Delete document"
                  className="
                    shrink-0 p-1.5 rounded-lg transition-colors
                    text-gray-300 dark:text-gray-700
                    hover:text-red-500 dark:hover:text-red-400
                    hover:bg-red-50 dark:hover:bg-red-900/20
                    opacity-0 group-hover:opacity-100
                  "
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )
          })}
        </div>

        {/* Inline deletion confirmation footer */}
        {pendingDelete && (
          <div className="shrink-0 border-t border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-5 py-4">
            <div className="flex items-start gap-2.5 mb-4">
              <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                  Delete {pendingName}?
                </p>
                <p className="text-xs text-red-600/70 dark:text-red-400/60 mt-1 leading-snug">
                  This removes the document and all its indexed vectors from the knowledge base.
                  This cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPendingDelete(null)}
                disabled={isDeleting}
                className="flex-1 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={isDeleting}
                className="flex-1 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isDeleting
                  ? <><Loader2 size={14} className="animate-spin" /> Deleting…</>
                  : <><Trash2 size={14} /> Delete</>
                }
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
