import { useState } from 'react'
import { FolderOpen, ChevronDown, RefreshCw, AlertCircle } from 'lucide-react'
import { useCollections } from '../hooks/useCollections'
import type { Collection } from '../types'

interface Props {
  selectedCollection: Collection | null
  onSelectCollection: (col: Collection | null) => void
}

export default function SidebarCollectionSection({ selectedCollection, onSelectCollection }: Props) {
  const [expanded, setExpanded] = useState(true)
  const { data: collections, isLoading, isError, refetch } = useCollections()

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
          Collections
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
        <div className="space-y-0.5 max-h-36 overflow-y-auto scrollbar-thin">
          {isLoading && (
            <div className="space-y-1.5 px-1 py-1">
              {[1, 2].map((i) => (
                <div key={i} className="h-7 rounded-md bg-gray-800 animate-pulse" />
              ))}
            </div>
          )}

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

          {!isLoading && !isError && collections && collections.length === 0 && (
            <p className="text-xs text-gray-500 px-2 py-2 text-center">
              No collections — manage via Files.
            </p>
          )}

          {collections?.map((col) => {
            const isSelected = selectedCollection?.collection_id === col.collection_id
            return (
              <button
                key={col.collection_id}
                onClick={() => onSelectCollection(isSelected ? null : col)}
                title={col.name}
                className={`
                  w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs
                  transition-colors text-left
                  ${isSelected ? 'bg-indigo-600 text-white' : 'text-gray-300 hover:bg-gray-800'}
                `}
              >
                <FolderOpen size={12} className="shrink-0" />
                <span className="flex-1 truncate">{col.name}</span>
                <span className={`shrink-0 text-[10px] ${isSelected ? 'text-indigo-200' : 'text-gray-500'}`}>
                  {col.document_ids.length}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
