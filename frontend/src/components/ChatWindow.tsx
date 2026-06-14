import { useRef, useEffect, useState, useCallback } from 'react'
import { MessageSquare, Zap, ChevronDown } from 'lucide-react'
import MessageBubble from './MessageBubble'
import type { ChatMessage, Collection, DocumentRecord } from '../types'

const EXAMPLE_PROMPTS = [
  'Summarize the key points of this document',
  'What are the main technical specifications?',
  'List all safety requirements mentioned',
  'What standards or regulations are referenced?',
]

interface Props {
  selectedDocument: DocumentRecord | null
  selectedCollection?: Collection | null
  messages: ChatMessage[]
  isLoading: boolean
  onSuggestPrompt?: (prompt: string) => void
  onDeleteMessage?: (msgId: string) => void
  onReactToMessage?: (msgId: string, r: 'like' | 'dislike') => void
  onRegenerate?: (assistantMsgId: string) => void
  onEditUserMessage?: (msgId: string, content: string) => void
}

export default function ChatWindow({
  selectedDocument,
  selectedCollection,
  messages,
  isLoading,
  onSuggestPrompt,
  onDeleteMessage,
  onReactToMessage,
  onRegenerate,
  onEditUserMessage,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)
  const [isAtBottom, setIsAtBottom] = useState(true)

  // Auto-scroll when new content arrives, but only if already at bottom.
  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollRef.current?.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [messages])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    const atBottom = distFromBottom < 80
    isAtBottomRef.current = atBottom
    setIsAtBottom(atBottom)
  }, [])

  function scrollToBottom() {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
    isAtBottomRef.current = true
    setIsAtBottom(true)
  }

  const contextLabel = selectedCollection
    ? selectedCollection.name
    : selectedDocument
      ? selectedDocument.filename
      : 'Industrial Document Intelligence'

  return (
    <div className="flex-1 flex flex-col bg-white dark:bg-gray-900 min-w-0 min-h-0 transition-colors duration-200 relative">
      {/* Desktop header */}
      <div className="hidden lg:flex px-4 lg:px-6 py-3 border-b border-gray-200 dark:border-gray-700 items-center gap-2 shrink-0">
        <MessageSquare size={16} className="text-indigo-600 shrink-0" />
        <span className="font-semibold text-gray-800 dark:text-gray-100 text-sm truncate">
          {contextLabel}
        </span>
        {(selectedDocument || selectedCollection) && (
          <span className="text-xs text-gray-400 ml-1 shrink-0">— ask a question below</span>
        )}
      </div>

      {/* Message list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin"
      >
        <div className="max-w-3xl mx-auto px-4 py-6">
          {messages.length === 0 && (
            <div className="min-h-[60vh] flex flex-col items-center justify-center gap-6 pb-8 select-none">
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    className="w-7 h-7 text-white"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </div>
                <div className="text-center">
                  <p className="text-base font-semibold text-gray-700 dark:text-gray-200">
                    {selectedDocument || selectedCollection
                      ? 'Ready to answer questions'
                      : 'Upload a document to get started'}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {selectedDocument
                      ? selectedDocument.filename
                      : selectedCollection
                        ? `${selectedCollection.name} · ${selectedCollection.document_ids.length} document${selectedCollection.document_ids.length !== 1 ? 's' : ''}`
                        : 'Use the + button below or select a file from the sidebar'}
                  </p>
                </div>
              </div>

              {(selectedDocument || selectedCollection) && onSuggestPrompt && (
                <div className="w-full max-w-lg">
                  <div className="flex items-center gap-1.5 mb-3 justify-center">
                    <Zap size={12} className="text-indigo-500" />
                    <span className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">
                      Try asking
                    </span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {EXAMPLE_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        onClick={() => onSuggestPrompt(prompt)}
                        className="
                          text-left px-4 py-3 rounded-xl text-sm leading-snug
                          border border-gray-200 dark:border-gray-700
                          bg-gray-50 dark:bg-gray-800/60
                          text-gray-600 dark:text-gray-300
                          hover:border-indigo-400 dark:hover:border-indigo-500
                          hover:bg-indigo-50 dark:hover:bg-indigo-900/20
                          hover:text-indigo-700 dark:hover:text-indigo-300
                          transition-colors
                        "
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Messages */}
          <div className="space-y-6">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onDelete={onDeleteMessage ? () => onDeleteMessage(msg.id) : undefined}
                onEdit={msg.role === 'user' && onEditUserMessage
                  ? () => onEditUserMessage(msg.id, msg.content)
                  : undefined
                }
                onRegenerate={msg.role === 'assistant' && onRegenerate
                  ? () => onRegenerate(msg.id)
                  : undefined
                }
                onReaction={msg.role === 'assistant' && onReactToMessage
                  ? (r) => onReactToMessage(msg.id, r)
                  : undefined
                }
              />
            ))}
          </div>

          {/* Bottom anchor */}
          <div className="h-4" />
        </div>
      </div>

      {/* Jump-to-bottom FAB */}
      {!isAtBottom && (
        <button
          onClick={scrollToBottom}
          aria-label="Jump to bottom"
          className="
            absolute bottom-4 right-4
            w-9 h-9 flex items-center justify-center
            rounded-full shadow-lg
            bg-white dark:bg-gray-800
            border border-gray-200 dark:border-gray-600
            text-gray-600 dark:text-gray-300
            hover:bg-gray-50 dark:hover:bg-gray-700
            transition-all
            z-10
          "
        >
          <ChevronDown size={18} />
          {isLoading && (
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-indigo-600 animate-pulse" />
          )}
        </button>
      )}
    </div>
  )
}
