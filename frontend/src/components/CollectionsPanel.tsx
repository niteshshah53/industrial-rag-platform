import { useState } from 'react'
import {
  X, Trash2, FolderOpen, AlertTriangle, Loader2, ChevronDown, ChevronRight,
  FileText, Check, FolderPlus,
} from 'lucide-react'
import {
  useCollections,
  useCreateCollection,
  useDeleteCollection,
  useAddDocumentToCollection,
  useRemoveDocumentFromCollection,
} from '../hooks/useCollections'
import { useDocuments } from '../hooks/useDocuments'
import type { Collection } from '../types'

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  isOpen: boolean
  onClose: () => void
  selectedCollectionId: string | null
  onCollectionDeleted: (id: string) => void
}

export default function CollectionsPanel({
  isOpen,
  onClose,
  selectedCollectionId,
  onCollectionDeleted,
}: Props) {
  const { data: collections = [], isLoading } = useCollections()
  const { data: docs = [] } = useDocuments()
  const { mutateAsync: createCollection, isPending: isCreating } = useCreateCollection()
  const { mutateAsync: deleteCollection, isPending: isDeleting } = useDeleteCollection()
  const { mutateAsync: addDoc } = useAddDocumentToCollection()
  const { mutateAsync: removeDoc } = useRemoveDocumentFromCollection()

  const [newName, setNewName] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Collection | null>(null)

  const readyDocs = docs.filter((d) => d.status === 'READY')

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    await createCollection({ name })
    setNewName('')
  }

  async function handleDelete() {
    if (!pendingDelete) return
    await deleteCollection(pendingDelete.collection_id)
    onCollectionDeleted(pendingDelete.collection_id)
    setPendingDelete(null)
  }

  async function toggleMember(collectionId: string, documentId: string, isMember: boolean) {
    if (isMember) {
      await removeDoc({ collectionId, documentId })
    } else {
      await addDoc({ collectionId, documentId })
    }
  }

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

      {/* Slide-in panel */}
      <div
        role="dialog"
        aria-label="Collection management"
        aria-modal="true"
        className={`
          fixed inset-y-0 right-0 z-50
          w-full sm:w-[480px]
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
            <FolderOpen size={18} className="text-indigo-600 shrink-0" />
            <div>
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Collections</h2>
              {!isLoading && (
                <p className="text-xs text-gray-400 leading-tight">
                  {collections.length === 0
                    ? 'No collections yet'
                    : `${collections.length} collection${collections.length !== 1 ? 's' : ''}`}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close collections panel"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Create new collection */}
        <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-800 shrink-0">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
            New collection
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="Collection name…"
              maxLength={100}
              className="
                flex-1 text-sm px-3 py-2 rounded-lg
                border border-gray-300 dark:border-gray-600
                bg-white dark:bg-gray-800
                text-gray-900 dark:text-gray-100
                placeholder-gray-400 dark:placeholder-gray-500
                focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent
              "
            />
            <button
              onClick={handleCreate}
              disabled={!newName.trim() || isCreating}
              className="
                shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg
                bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40
                text-white text-sm font-medium transition-colors
              "
            >
              {isCreating ? <Loader2 size={14} className="animate-spin" /> : <FolderPlus size={14} />}
              Create
            </button>
          </div>
        </div>

        {/* Collection list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 size={24} className="animate-spin text-indigo-600" />
            </div>
          )}

          {!isLoading && collections.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <FolderOpen size={40} className="text-gray-200 dark:text-gray-700 mb-3" />
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                No collections yet
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                Create one above to group documents for multi-document queries.
              </p>
            </div>
          )}

          {collections.map((col) => {
            const isActive = col.collection_id === selectedCollectionId
            const isExpanded = expandedId === col.collection_id

            return (
              <div
                key={col.collection_id}
                className="border-b border-gray-100 dark:border-gray-800"
              >
                {/* Collection header row */}
                <div
                  className={`
                    flex items-center gap-2.5 px-5 py-3 group
                    ${isActive ? 'bg-indigo-50/60 dark:bg-indigo-900/10' : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'}
                  `}
                >
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : col.collection_id)}
                    className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    {isExpanded
                      ? <ChevronDown size={16} />
                      : <ChevronRight size={16} />
                    }
                  </button>

                  <FolderOpen size={16} className={`shrink-0 ${isActive ? 'text-indigo-600' : 'text-gray-400'}`} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                        {col.name}
                      </p>
                      {isActive && (
                        <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400 bg-indigo-100 dark:bg-indigo-900/40 px-1.5 py-0.5 rounded">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {col.document_ids.length} document{col.document_ids.length !== 1 ? 's' : ''}
                    </p>
                  </div>

                  <button
                    onClick={() => setPendingDelete(col)}
                    title="Delete collection"
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

                {/* Expanded: document membership checklist */}
                {isExpanded && (
                  <div className="px-5 pb-3 pt-1 bg-gray-50/50 dark:bg-gray-800/30">
                    {readyDocs.length === 0 ? (
                      <p className="text-xs text-gray-400 py-2">
                        No ready documents available to add.
                      </p>
                    ) : (
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
                          Members — click to add or remove:
                        </p>
                        {readyDocs.map((doc) => {
                          const isMember = col.document_ids.includes(doc.document_id)
                          return (
                            <button
                              key={doc.document_id}
                              onClick={() => toggleMember(col.collection_id, doc.document_id, isMember)}
                              className="
                                w-full flex items-center gap-2.5 px-3 py-2 rounded-lg
                                text-left text-xs transition-colors
                                hover:bg-gray-100 dark:hover:bg-gray-700
                                text-gray-700 dark:text-gray-300
                              "
                            >
                              <div className={`
                                w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors
                                ${isMember
                                  ? 'bg-indigo-600 border-indigo-600'
                                  : 'border-gray-300 dark:border-gray-600'}
                              `}>
                                {isMember && <Check size={10} className="text-white" />}
                              </div>
                              <FileText size={12} className="shrink-0 text-gray-400" />
                              <span className="truncate flex-1">{doc.filename}</span>
                              <span className="shrink-0 text-gray-400">
                                {doc.chunk_count} chunks
                              </span>
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Delete confirmation footer */}
        {pendingDelete && (
          <div className="shrink-0 border-t border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-5 py-4">
            <div className="flex items-start gap-2.5 mb-4">
              <AlertTriangle size={16} className="text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">
                  Delete &ldquo;{pendingDelete.name}&rdquo;?
                </p>
                <p className="text-xs text-red-600/70 dark:text-red-400/60 mt-1 leading-snug">
                  The collection grouping will be removed. The documents themselves are not affected.
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
                onClick={handleDelete}
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
