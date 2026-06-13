import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import type { AppSettings, Theme } from '../types'

const SETTINGS_KEY = 'rag_app_settings'

const DEFAULTS: AppSettings = {
  topK: 5,
  threshold: 0.3,
  theme: 'system',
}

function load(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

function persist(s: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(s))
  } catch {}
}

// ── Context ────────────────────────────────────────────────────────────────────

interface SettingsContextValue {
  settings: AppSettings
  setTopK: (v: number) => void
  setThreshold: (v: number) => void
  setTheme: (v: Theme) => void
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

// ── Provider ───────────────────────────────────────────────────────────────────

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(load)

  const update = useCallback((patch: Partial<AppSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch }
      persist(next)
      return next
    })
  }, [])

  return (
    <SettingsContext.Provider
      value={{
        settings,
        setTopK: (topK) => update({ topK }),
        setThreshold: (threshold) => update({ threshold }),
        setTheme: (theme) => update({ theme }),
      }}
    >
      {children}
    </SettingsContext.Provider>
  )
}

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used inside <SettingsProvider>')
  return ctx
}
