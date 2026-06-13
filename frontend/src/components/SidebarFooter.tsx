import { Settings } from 'lucide-react'

interface Props {
  onOpenSettings: () => void
}

export default function SidebarFooter({ onOpenSettings }: Props) {
  return (
    <div className="shrink-0 border-t border-gray-700 px-3 py-3 flex items-center gap-2">
      <button
        onClick={onOpenSettings}
        title="Settings"
        className="p-2 text-gray-400 hover:text-gray-100 hover:bg-gray-800 rounded-lg transition-colors"
      >
        <Settings size={18} />
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
