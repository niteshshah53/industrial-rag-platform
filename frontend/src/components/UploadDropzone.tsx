import { useRef, useState, DragEvent } from 'react'
import { Upload, Loader2 } from 'lucide-react'
import { useUploadDocument } from '../hooks/useDocuments'

const ACCEPTED = '.pdf,.docx,.txt'
const ACCEPTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain']

export default function UploadDropzone() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { mutate: upload, isPending } = useUploadDocument()

  function handleFile(file: File) {
    setError(null)
    const ext = file.name.split('.').pop()?.toLowerCase()
    const validExt = ['pdf', 'docx', 'txt'].includes(ext ?? '')
    const validType = ACCEPTED_TYPES.includes(file.type) || file.type === ''

    if (!validExt && !validType) {
      setError('Unsupported file type. Upload a PDF, DOCX, or TXT file.')
      return
    }

    upload(file, {
      onError: (err) => setError(err instanceof Error ? err.message : 'Upload failed'),
    })
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="px-3 pb-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !isPending && inputRef.current?.click()}
        className={`
          cursor-pointer border-2 border-dashed rounded-xl p-4 text-center transition-colors
          ${dragging ? 'border-indigo-400 bg-indigo-50' : 'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'}
          ${isPending ? 'opacity-50 cursor-not-allowed' : ''}
        `}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleFile(file)
            e.target.value = ''
          }}
        />

        {isPending ? (
          <span className="flex flex-col items-center gap-1 text-indigo-600 text-xs">
            <Loader2 size={20} className="animate-spin" />
            Uploading…
          </span>
        ) : (
          <span className="flex flex-col items-center gap-1 text-gray-500 text-xs">
            <Upload size={20} />
            <span>Drop file or click to upload</span>
            <span className="text-gray-400">PDF · DOCX · TXT</span>
          </span>
        )}
      </div>

      {error && (
        <p className="mt-1.5 text-xs text-red-600 text-center">{error}</p>
      )}
    </div>
  )
}
