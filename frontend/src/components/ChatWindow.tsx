import { useRef, useEffect, useState, KeyboardEvent } from 'react'
import { Send, MessageSquare } from 'lucide-react'
import MessageBubble from './MessageBubble'
import { useChat } from '../hooks/useChat'
import type { DocumentRecord } from '../types'

interface Props {
  selectedDocument: DocumentRecord | null
}

export default function ChatWindow({ selectedDocument }: Props) {
  const { messages, sendMessage, isLoading } = useChat(0.5)
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSend() {
    const q = input.trim()
    if (!q || isLoading) return
    setInput('')
    sendMessage(q)
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  const disabled = !selectedDocument || selectedDocument.status !== 'ready'

  return (
    <div className="flex-1 flex flex-col bg-white min-w-0">
      {/* Header */}
      <div className="px-6 py-3 border-b border-gray-200 flex items-center gap-2">
        <MessageSquare size={16} className="text-indigo-600" />
        <span className="font-semibold text-gray-800 text-sm">
          {selectedDocument
            ? selectedDocument.filename
            : 'Industrial Document Intelligence'}
        </span>
        {selectedDocument && (
          <span className="text-xs text-gray-400 ml-1">— select from sidebar or upload to begin</span>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 select-none">
            <MessageSquare size={40} className="mb-3 opacity-30" />
            <p className="text-sm font-medium">Ask a question about your document</p>
            <p className="text-xs mt-1">
              {disabled
                ? 'Select a ready document from the sidebar first'
                : `Chatting with: ${selectedDocument?.filename}`}
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="px-6 py-4 border-t border-gray-200">
        {disabled && (
          <p className="text-xs text-amber-600 mb-2 text-center">
            {!selectedDocument
              ? 'Select a document from the sidebar to start chatting.'
              : 'This document is still processing. Wait until status is Ready.'}
          </p>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onInput={handleInput}
            onKeyDown={handleKeyDown}
            disabled={disabled || isLoading}
            placeholder={disabled ? 'Select a ready document first…' : 'Ask a question… (Enter to send, Shift+Enter for newline)'}
            className="
              flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm
              focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent
              disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed
              scrollbar-thin
            "
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading || disabled}
            className="
              shrink-0 w-10 h-10 flex items-center justify-center
              rounded-xl bg-indigo-600 text-white
              hover:bg-indigo-700 active:scale-95 transition-all
              disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100
            "
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
