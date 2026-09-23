import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { uz, type Resources } from './uz'

export const DEFAULT_LOCALE = 'uz'

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation'
    resources: { translation: Resources }
  }
}

void i18n.use(initReactI18next).init({
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [DEFAULT_LOCALE],
  resources: { uz: { translation: uz } },
  interpolation: { escapeValue: false },
  returnNull: false,
  initAsync: false,
})

export default i18n
