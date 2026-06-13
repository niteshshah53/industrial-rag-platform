import { useEffect } from 'react'
import { useSettings } from '../contexts/settings'
import type { Theme } from '../types'

function applyThemeClass(theme: Theme, mediaQuery: MediaQueryList): void {
  const root = document.documentElement
  if (theme === 'dark') {
    root.classList.add('dark')
  } else if (theme === 'light') {
    root.classList.remove('dark')
  } else {
    // system — follow OS preference
    mediaQuery.matches ? root.classList.add('dark') : root.classList.remove('dark')
  }
}

export function useTheme() {
  const { settings, setTheme } = useSettings()
  const { theme } = settings

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

    applyThemeClass(theme, mediaQuery)

    if (theme !== 'system') return

    const handler = () => applyThemeClass(theme, mediaQuery)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [theme])

  return { theme, setTheme }
}
