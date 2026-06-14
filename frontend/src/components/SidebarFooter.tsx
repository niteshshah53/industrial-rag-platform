import { Settings, Files, FolderOpen } from 'lucide-react'

interface Props {
  onOpenSettings: () => void
  onOpenDocuments: () => void
  onOpenCollections: () => void
}

export default function SidebarFooter({ onOpenSettings, onOpenDocuments, onOpenCollections }: Props) {
  return (
    <div className="shrink-0 border-t border-gray-700 px-3 py-3 flex items-center gap-1">
      <button
        onClick={onOpenSettings}
        title="Settings"
        aria-label="Settings"
        className="p-2 text-gray-400 hover:text-gray-100 hover:bg-gray-800 rounded-lg transition-colors"
      >
        <Settings size={18} />
      </button>
      <button
        onClick={onOpenDocuments}
        title="Manage documents"
        aria-label="Manage documents"
        className="p-2 text-gray-400 hover:text-gray-100 hover:bg-gray-800 rounded-lg transition-colors"
      >
        <Files size={18} />
      </button>
      <button
        onClick={onOpenCollections}
        title="Manage collections"
        aria-label="Manage collections"
        className="p-2 text-gray-400 hover:text-gray-100 hover:bg-gray-800 rounded-lg transition-colors"
      >
        <FolderOpen size={18} />
      </button>
      <div className="flex-1" />
      <div
        title="Account"
        className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center cursor-default select-none shrink-0"
      >
        <span className="text-white text-xs font-semibold">U</span>
      </div>
    </div>
  )
}
