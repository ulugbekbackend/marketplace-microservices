import '@bozorcha/ui/fonts'
import './app.css'
import './i18n'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'

const container = document.getElementById('root')
if (!container) throw new Error('Root element #root is missing')

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
