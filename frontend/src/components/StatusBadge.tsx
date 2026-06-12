import type { DocumentStatus } from '../types'

interface Props {
  status: DocumentStatus
}

const CONFIG: Record<DocumentStatus, { label: string; classes: string }> = {
  pending:    { label: 'Pending',    classes: 'bg-yellow-100 text-yellow-800' },
  processing: { label: 'Processing', classes: 'bg-blue-100 text-blue-800 animate-pulse' },
  ready:      { label: 'Ready',      classes: 'bg-green-100 text-green-800' },
  failed:     { label: 'Failed',     classes: 'bg-red-100 text-red-800' },
}

export default function StatusBadge({ status }: Props) {
  const { label, classes } = CONFIG[status] ?? CONFIG.failed
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${classes}`}>
      {label}
    </span>
  )
}
