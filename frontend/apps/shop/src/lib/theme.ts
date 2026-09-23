import { useEffect } from 'react'
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeMode = 'system' | 'light' | 'dark'

type ThemeState = {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
}

/** UI-only state: the chosen colour scheme, persisted. Defaults to the system setting. */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: 'system',
      setMode: (mode) => set({ mode }),
    }),
    { name: 'bozorcha.theme', partialize: (state) => ({ mode: state.mode }) },
  ),
)

const darkQuery = () =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

export function resolveDark(mode: ThemeMode): boolean {
  if (mode === 'system') return darkQuery()?.matches ?? false
  return mode === 'dark'
}

/** Keeps `<html class="dark">` in sync with the store and, in system mode, with the OS. */
export function useApplyTheme(): void {
  const mode = useThemeStore((state) => state.mode)
  useEffect(() => {
    const apply = () => document.documentElement.classList.toggle('dark', resolveDark(mode))
    apply()
    if (mode !== 'system') return
    const query = darkQuery()
    query?.addEventListener('change', apply)
    return () => query?.removeEventListener('change', apply)
  }, [mode])
}
