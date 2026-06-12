import { useState } from 'react'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import type { Citation } from '../types'

interface Props {
  citations: Citation[]
}

export default function CitationCard({ citations }: Props) {
  const [open, setOpen] = useState(false)

  if (citations.length === 0) return null

  return (
    <div className="mt-2 border border-gray-200 rounded-lg overflow-hidden text-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
      >
        <span className="flex items-center gap-1.5 font-medium text-gray-600">
          <FileText size={14} />
          {citations.length} source{citations.length > 1 ? 's' : ''}
        </span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <ul className="divide-y divide-gray-100">
          {citations.map((c, i) => (
            <li key={i} className="px-3 py-2 flex items-start gap-2 bg-white">
              <span className="mt-0.5 shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold">
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-gray-800 truncate">{c.document_name}</p>
                <p className="text-gray-500 text-xs">
                  Page {c.page_number} &middot; score {c.relevance_score.toFixed(3)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
