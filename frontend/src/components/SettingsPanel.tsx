import type { ReactNode, ElementType } from 'react'
import { X, Cpu, SlidersHorizontal, Palette, Info } from 'lucide-react'
import ModelSettings from './ModelSettings'
import RetrievalSettings from './RetrievalSettings'
import ThemeSettings from './ThemeSettings'

interface SectionProps {
  title: string
  Icon: ElementType
  children: ReactNode
}

function Section({ title, Icon, children }: SectionProps) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Icon size={15} className="text-indigo-600 dark:text-indigo-400 shrink-0" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wide">
          {title}
        </h3>
      </div>
      {children}
    </div>
  )
}

interface Props {
  isOpen: boolean
  onClose: () => void
}

export default function SettingsPanel({ isOpen, onClose }: Props) {
  return (
    <>
      {/* Backdrop — covers the whole screen, closes panel on click */}
      <div
        className={`
          fixed inset-0 bg-black/40 z-40
          transition-opacity duration-200
          ${isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}
        `}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-in panel */}
      <div
        role="dialog"
        aria-label="Settings"
        aria-modal="true"
        className={`
          fixed inset-y-0 left-0 z-50 w-full sm:w-80
          bg-white dark:bg-gray-900
          border-r border-gray-200 dark:border-gray-700
          flex flex-col shadow-2xl
          transform transition-transform duration-200 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-6 space-y-8">
          <Section title="Model" Icon={Cpu}>
            <ModelSettings />
          </Section>

          <Section title="Retrieval" Icon={SlidersHorizontal}>
            <RetrievalSettings />
          </Section>

          <Section title="Appearance" Icon={Palette}>
            <ThemeSettings />
          </Section>

          <Section title="About" Icon={Info}>
            <div className="space-y-0">
              {[
                { label: 'Version', value: '1.0.0' },
                { label: 'Framework', value: 'FastAPI + LangGraph' },
                { label: 'Vector DB', value: 'Qdrant' },
                { label: 'LLM Runtime', value: 'Ollama' },
              ].map(({ label, value }) => (
                <div
                  key={label}
                  className="flex items-center justify-between py-2.5 border-b border-gray-100 dark:border-gray-700 last:border-0"
                >
                  <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
                  <span className="text-sm text-gray-900 dark:text-gray-100">{value}</span>
                </div>
              ))}
            </div>
          </Section>
        </div>
      </div>
    </>
  )
}
