import { useSettings } from '../contexts/settings'

interface SliderRowProps {
  label: string
  hint: string
  min: number
  max: number
  step: number
  value: number
  display: string
  onChange: (v: number) => void
}

function SliderRow({ label, hint, min, max, step, value, display, onChange }: SliderRowProps) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
        <span className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 tabular-nums min-w-[2.5rem] text-right">
          {display}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-indigo-600 cursor-pointer"
      />
      <p className="mt-1 text-xs text-gray-400">{hint}</p>
    </div>
  )
}

export default function RetrievalSettings() {
  const { settings, setTopK, setThreshold, setSearchMode } = useSettings()

  return (
    <div className="space-y-6">
      {/* Search mode toggle */}
      <div>
        <p className="text-sm text-gray-700 dark:text-gray-300 mb-2">Search Mode</p>
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {(['hybrid', 'dense'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setSearchMode(mode)}
              className={`
                flex-1 py-2 text-sm font-medium transition-colors
                ${settings.searchMode === mode
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                }
              `}
            >
              {mode === 'hybrid' ? 'Hybrid (BM25 + Vector)' : 'Dense (Vector only)'}
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-400">
          {settings.searchMode === 'hybrid'
            ? 'Combines keyword matching (BM25) with semantic similarity — better for technical terms'
            : 'Pure vector similarity — better for conceptual / paraphrase queries'}
        </p>
      </div>

      <SliderRow
        label="Top Results"
        hint="Number of document chunks retrieved per query"
        min={1}
        max={10}
        step={1}
        value={settings.topK}
        display={String(settings.topK)}
        onChange={setTopK}
      />
      <SliderRow
        label="Min Similarity"
        hint="Minimum cosine similarity score for retrieved chunks (lower = more results)"
        min={0}
        max={1}
        step={0.05}
        value={settings.threshold}
        display={settings.threshold.toFixed(2)}
        onChange={setThreshold}
      />
    </div>
  )
}
