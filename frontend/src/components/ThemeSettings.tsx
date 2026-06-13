import { Sun, Moon, Monitor } from 'lucide-react'
import { useSettings } from '../contexts/settings'
import type { Theme } from '../types'

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Monitor },
]

export default function ThemeSettings() {
  const { settings, setTheme } = useSettings()

  return (
    <div className="flex gap-2">
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = settings.theme === value
        return (
          <button
            key={value}
            onClick={() => setTheme(value)}
            aria-pressed={active}
            className={`
              flex-1 flex flex-col items-center gap-1.5 py-3 rounded-xl border
              text-xs font-medium transition-all
              ${active
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                : 'border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'
              }
            `}
          >
            <Icon size={18} />
            {label}
          </button>
        )
      })}
    </div>
  )
}
