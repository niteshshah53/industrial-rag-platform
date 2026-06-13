import { useState } from 'react'
import { ChevronDown, ChevronRight, ChevronUp, FileText } from 'lucide-react'
import type { Citation } from '../types'

interface Props {
  citations: Citation[]
}

export default function CitationCard({ citations }: Props) {
  // Outer toggle — show/hide the citation list
  const [open, setOpen] = useState(false)
  // Per-citation expand — which rows show the full passage
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (citations.length === 0) return null

  function toggleExpand(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  return (
    <div className="mt-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden text-sm">
      {/* Header row — collapses/expands the full list */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="
          w-full flex items-center justify-between px-3 py-2 text-left
          bg-gray-50 dark:bg-gray-800/80
          hover:bg-gray-100 dark:hover:bg-gray-700
          transition-colors
        "
      >
        <span className="flex items-center gap-1.5 font-medium text-gray-600 dark:text-gray-300">
          <FileText size={14} />
          {citations.length} source{citations.length > 1 ? 's' : ''}
        </span>
        {open
          ? <ChevronDown size={14} className="text-gray-400 dark:text-gray-500" />
          : <ChevronRight size={14} className="text-gray-400 dark:text-gray-500" />
        }
      </button>

      {open && (
        <ul className="divide-y divide-gray-100 dark:divide-gray-700">
          {citations.map((c, i) => {
            const isExpanded = expanded.has(i)
            return (
              <li key={i} className="bg-white dark:bg-gray-800">
                {/* Citation metadata row */}
                <div className="px-3 py-2.5 flex items-start gap-2">
                  <span className="mt-0.5 shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 text-xs font-bold">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-800 dark:text-gray-200 truncate">
                      {c.document_name}
                    </p>
                    <p className="text-gray-500 dark:text-gray-400 text-xs">
                      Page {c.page_number} &middot; score {c.relevance_score.toFixed(3)}
                    </p>

                    {/* Snippet preview — always visible, click to see more */}
                    {c.snippet && !isExpanded && (
                      <p className="
                        mt-1.5 text-xs text-gray-500 dark:text-gray-400 leading-relaxed
                        border-l-2 border-gray-200 dark:border-gray-700 pl-2
                        break-words
                      ">
                        {c.snippet}
                      </p>
                    )}

                    {/* Toggle button */}
                    {c.text && (
                      <button
                        onClick={() => toggleExpand(i)}
                        className="mt-1.5 flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
                      >
                        {isExpanded
                          ? <><ChevronUp size={11} /> Hide passage</>
                          : <><ChevronDown size={11} /> Show full passage</>
                        }
                      </button>
                    )}
                  </div>
                </div>

                {/* Full passage — expands below the metadata row */}
                {isExpanded && c.text && (
                  <div className="px-3 pb-3">
                    <div className="
                      rounded-lg border border-gray-200 dark:border-gray-700
                      bg-gray-50 dark:bg-gray-900/60
                      px-3 py-2.5
                      max-h-56 overflow-y-auto scrollbar-thin
                    ">
                      <p className="
                        text-xs text-gray-700 dark:text-gray-300
                        leading-relaxed whitespace-pre-wrap break-words
                        font-mono
                      ">
                        {c.text}
                      </p>
                    </div>
                    <p className="mt-1 text-[10px] text-gray-400 dark:text-gray-600">
                      Raw text extracted from PDF — spacing may vary for multi-column documents.
                    </p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
