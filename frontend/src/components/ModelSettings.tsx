import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { listDocuments } from '../api/client'

// Uses the documents endpoint as a backend health probe — if it responds, the
// backend (and by extension Ollama + Qdrant) are reachable.
function useBackendHealth() {
  return useQuery({
    queryKey: ['health-probe'],
    queryFn: listDocuments,
    retry: 1,
    refetchInterval: 30_000,
    staleTime: 30_000,
  })
}

interface RowProps {
  label: string
  value: React.ReactNode
}

function Row({ label, value }: RowProps) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      <span className="text-sm text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  )
}

export default function ModelSettings() {
  const { isSuccess, isError, isPending } = useBackendHealth()

  const statusNode = (
    <span className="flex items-center gap-1.5">
      {isPending && <Loader2 size={13} className="animate-spin text-gray-400" />}
      {isSuccess && <CheckCircle2 size={13} className="text-green-500" />}
      {isError && <XCircle size={13} className="text-red-500" />}
      <span
        className={
          isSuccess ? 'text-green-600 dark:text-green-400'
          : isError ? 'text-red-500'
          : 'text-gray-400'
        }
      >
        {isPending ? 'Checking…' : isSuccess ? 'Online' : 'Offline'}
      </span>
    </span>
  )

  return (
    <div>
      <Row
        label="LLM Model"
        value={
          <code className="text-xs font-mono bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
            llama3.2:3b
          </code>
        }
      />
      <Row
        label="Embedding Model"
        value={
          <code className="text-xs font-mono bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
            nomic-embed-text
          </code>
        }
      />
      <Row label="Vector Store" value="Qdrant" />
      <Row label="Backend Status" value={statusNode} />
    </div>
  )
}
