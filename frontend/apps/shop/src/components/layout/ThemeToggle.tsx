import { Moon, Sun } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { useThemeStore } from '../../lib/theme'

const subscribeToClass = (callback: () => void) => {
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => observer.disconnect()
}
const isDarkNow = () => document.documentElement.classList.contains('dark')

/** Flips between light and dark; the first choice replaces the system default and is saved. */
export function ThemeToggle() {
  const { t } = useTranslation()
  const setMode = useThemeStore((state) => state.setMode)
  const dark = useSyncExternalStore(subscribeToClass, isDarkNow, () => false)
  const label = dark ? t('header.themeToLight') : t('header.themeToDark')

  return (
    <button
      type="button"
      onClick={() => setMode(dark ? 'light' : 'dark')}
      aria-label={label}
      title={label}
      className="grid size-11 shrink-0 place-items-center rounded-lg text-text transition-colors duration-150 ease-out hover:bg-surface-2 focus-ring"
    >
      {dark ? (
        <Sun aria-hidden="true" size={20} strokeWidth={1.75} />
      ) : (
        <Moon aria-hidden="true" size={20} strokeWidth={1.75} />
      )}
    </button>
  )
}
