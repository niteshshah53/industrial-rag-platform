import { useRef } from 'react'
import { FileText } from 'lucide-react'

const ACCEPTED = '.pdf,.docx,.txt'
const ACCEPTED_MIME = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
])

interface Props {
  isOpen: boolean
  onFileSelected: (file: File) => void
}

function isValidFile(file: File): boolean {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  return ['pdf', 'docx', 'txt'].includes(ext) || ACCEPTED_MIME.has(file.type)
}

export default function UploadPopover({ isOpen, onFileSelected }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file && isValidFile(file)) onFileSelected(file)
  }

  return (
    <>
      {/* Hidden file input — always mounted so the ref is stable */}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={handleChange}
      />

      {/* Popover — kept in DOM; shown/hidden via opacity + scale for a smooth entrance */}
      <div
        className={`
          absolute bottom-full left-0 mb-2 z-50
          bg-white dark:bg-gray-800
          border border-gray-200 dark:border-gray-600
          rounded-xl shadow-lg overflow-hidden
          min-w-[190px]
          transform transition-all duration-150 origin-bottom-left
          ${isOpen
            ? 'opacity-100 scale-100 pointer-events-auto'
            : 'opacity-0 scale-95 pointer-events-none'}
        `}
      >
        <button
          onClick={() => inputRef.current?.click()}
          className="
            w-full flex items-center gap-3 px-4 py-3
            text-sm text-gray-700 dark:text-gray-200
            hover:bg-gray-50 dark:hover:bg-gray-700
            transition-colors text-left
          "
        >
          <FileText size={16} className="text-indigo-600 shrink-0" />
          Upload Document
          <span className="ml-auto text-xs text-gray-400">PDF · DOCX · TXT</span>
        </button>
      </div>
    </>
  )
}
