import { createContext, useContext, useState, useEffect } from 'react'

const ThemeContext = createContext({ theme: 'dark', toggle: () => {} })

const THEMES = {
  dark:    { label: 'Dark',     s0:'#0B1120', s1:'#111827', s2:'#1A2235', s3:'#243044', s4:'#2D3B52' },
  amoled:  { label: 'AMOLED',   s0:'#000000', s1:'#0A0A0A', s2:'#111111', s3:'#1A1A1A', s4:'#222222' },
  ocean:   { label: 'Ocean',    s0:'#0A1628', s1:'#0F1F38', s2:'#152847', s3:'#1C3358', s4:'#233E69' },
  light:   { label: 'Light',    s0:'#F8FAFC', s1:'#FFFFFF', s2:'#FFFFFF', s3:'#F1F5F9', s4:'#E2E8F0' },
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('alchemy-theme') || 'dark'
    }
    return 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    const t = THEMES[theme] || THEMES.dark

    // Apply CSS custom properties
    root.style.setProperty('--surface-0', t.s0)
    root.style.setProperty('--surface-1', t.s1)
    root.style.setProperty('--surface-2', t.s2)
    root.style.setProperty('--surface-3', t.s3)
    root.style.setProperty('--surface-4', t.s4)
    document.body.style.background = t.s0

    // Light/dark class
    if (theme === 'light') {
      root.classList.remove('dark')
      root.classList.add('light')
    } else {
      root.classList.add('dark')
      root.classList.remove('light')
    }

    localStorage.setItem('alchemy-theme', theme)
  }, [theme])

  const toggle = () => {
    const keys = Object.keys(THEMES)
    const i = keys.indexOf(theme)
    setTheme(keys[(i + 1) % keys.length])
  }

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme, themes: THEMES }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
