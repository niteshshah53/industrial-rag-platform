import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Plus, Send, Loader2, FileText, X, CheckCircle2, AlertCircle } from 'lucide-react'
import UploadPopover from './UploadPopover'
import { useUploadDocument, useDocuments } from '../hooks/useDocuments'
import type { DocumentRecord } from '../types'

type ChipStatus = 'uploading' | 'processing' | 'ready' | 'error'

interface Chip {
  filename: string
  status: ChipStatus
  message?: string
}

interface Props {
  /** True when no ready document is selected — disables textarea + send, not the + button. */
  disabled: boolean
  isLoading: boolean
  onSend: (text: string) => void
  /** Called once the newly uploaded document has finished processing and is ready. */
  onDocumentUploaded: (doc: DocumentRecord) => void
  /** Pre-fills the textarea (e.g. from an example prompt card). Consumed once applied. */
  suggestedInput?: string
  onSuggestConsumed?: () => void
}

export default function ChatInputBar({
  disabled,
  isLoading,
  onSend,
  onDocumentUploaded,
  suggestedInput,
  onSuggestConsumed,
}: Props) {
  const [input, setInput] = useState('')
  const [popoverOpen, setPopoverOpen] = useState(false)
  const [chip, setChip] = useState<Chip | null>(null)
  const [uploadedDocId, setUploadedDocId] = useState<string | null>(null)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const plusWrapperRef = useRef<HTMLDivElement>(null)

  const { mutate: upload } = useUploadDocument()
  const { data: docs } = useDocuments()

  // Apply a suggested prompt from the empty-state example cards
  useEffect(() => {
    if (!suggestedInput) return
    setInput(suggestedInput)
    onSuggestConsumed?.()
    // Defer focus so the state update has rendered first
    setTimeout(() => {
      const el = textareaRef.current
      if (!el) return
      el.focus()
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`
    }, 0)
  }, [suggestedInput, onSuggestConsumed])

  // Close popover when user clicks outside the + button wrapper
  useEffect(() => {
    if (!popoverOpen) return
    function onMouseDown(e: MouseEvent) {
      if (plusWrapperRef.current && !plusWrapperRef.current.contains(e.target as Node)) {
        setPopoverOpen(false)
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [popoverOpen])

  // Watch for the uploaded doc to become ready, then auto-select it
  useEffect(() => {
    if (!uploadedDocId || !docs) return
    const doc = docs.find((d) => d.document_id === uploadedDocId)
    if (!doc) return

    if (doc.status === 'ready') {
      setChip({ filename: doc.filename, status: 'ready', message: 'Ready' })
      onDocumentUploaded(doc)
      setUploadedDocId(null)
      const timer = setTimeout(() => setChip(null), 3000)
      return () => clearTimeout(timer)
    }

    if (doc.status === 'failed') {
      setChip({ filename: doc.filename, status: 'error', message: doc.error_message ?? 'Processing failed' })
      setUploadedDocId(null)
    }
  }, [docs, uploadedDocId, onDocumentUploaded])

  function handleFileSelected(file: File) {
    setPopoverOpen(false)
    setChip({ filename: file.name, status: 'uploading', message: 'Uploading…' })
    upload(file, {
      onSuccess: (res) => {
        setUploadedDocId(res.document_id)
        setChip({ filename: file.name, status: 'processing', message: 'Processing…' })
      },
      onError: (err) => {
        setChip({
          filename: file.name,
          status: 'error',
          message: err instanceof Error ? err.message : 'Upload failed',
        })
      },
    })
  }

  function handleSend() {
    const q = input.trim()
    if (!q || isLoading || disabled) return
    setInput('')
    onSend(q)
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.focus()
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleTextareaInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }

  const chipIconClass = {
    uploading: 'text-indigo-600',
    processing: 'text-blue-500',
    ready: 'text-green-600',
    error: 'text-red-500',
  }

  return (
    <div className="shrink-0 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 pb-safe pt-3">
      {/* Upload progress chip */}
      {chip && (
        <div className="mb-3 max-w-4xl mx-auto flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-xs">
          {chip.status === 'uploading' && (
            <Loader2 size={14} className="animate-spin text-indigo-600 shrink-0" />
          )}
          {chip.status === 'processing' && (
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shrink-0" />
          )}
          {chip.status === 'ready' && (
            <CheckCircle2 size={14} className="text-green-600 shrink-0" />
          )}
          {chip.status === 'error' && (
            <AlertCircle size={14} className="text-red-500 shrink-0" />
          )}

          <FileText size={13} className="text-gray-400 shrink-0" />
          <span className="truncate text-gray-700 dark:text-gray-300 flex-1 min-w-0">
            {chip.filename}
          </span>
          <span className={`shrink-0 font-medium ${chipIconClass[chip.status]}`}>
            {chip.message}
          </span>

          {(chip.status === 'error' || chip.status === 'ready') && (
            <button
              onClick={() => setChip(null)}
              aria-label="Dismiss"
              className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 ml-1"
            >
              <X size={13} />
            </button>
          )}
        </div>
      )}

      {/* Hint when no doc is selected and nothing is uploading */}
      {disabled && !chip && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mb-2 text-center">
          Use <strong>+</strong> to upload a document, or select one from the sidebar.
        </p>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2 max-w-4xl mx-auto">
        {/* + button with upload popover */}
        <div ref={plusWrapperRef} className="relative shrink-0 self-end">
          <UploadPopover
            isOpen={popoverOpen}
            onFileSelected={handleFileSelected}
          />
          <button
            onClick={() => setPopoverOpen((prev) => !prev)}
            title="Upload document"
            aria-label="Upload document"
            aria-expanded={popoverOpen}
            className="
              w-10 h-10 flex items-center justify-center rounded-xl
              border border-gray-300 dark:border-gray-600
              text-gray-500 dark:text-gray-400
              hover:bg-gray-100 dark:hover:bg-gray-800
              hover:text-indigo-600 dark:hover:text-indigo-400
              hover:border-indigo-400 dark:hover:border-indigo-500
              transition-colors active:scale-95
            "
          >
            <Plus size={18} />
          </button>
        </div>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onInput={handleTextareaInput}
          onKeyDown={handleKeyDown}
          disabled={disabled || isLoading}
          placeholder={
            disabled
              ? 'Upload or select a document to start chatting…'
              : 'Ask a question… (Enter to send, Shift+Enter for newline)'
          }
          className="
            flex-1 resize-none rounded-xl
            border border-gray-300 dark:border-gray-600
            px-4 py-2.5 text-sm
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent
            disabled:bg-gray-50 dark:disabled:bg-gray-800/50
            disabled:text-gray-400 disabled:cursor-not-allowed
            scrollbar-thin transition-colors
          "
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!input.trim() || isLoading || disabled}
          aria-label="Send message"
          className="
            shrink-0 w-10 h-10 flex items-center justify-center self-end
            rounded-xl bg-indigo-600 text-white
            hover:bg-indigo-700 active:scale-95 transition-all
            disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100
          "
        >
          {isLoading
            ? <Loader2 size={16} className="animate-spin" />
            : <Send size={16} />
          }
        </button>
      </div>
    </div>
  )
}
