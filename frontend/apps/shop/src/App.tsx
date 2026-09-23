import { ApiProvider } from '@bozorcha/api-client'
import { ToastProvider } from '@bozorcha/ui'
import { QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { RouterProvider } from 'react-router/dom'
import { apiClient, queryClient } from './lib/api'
import { router } from './routes'

export function App() {
  const { t } = useTranslation()
  return (
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={apiClient}>
        <ToastProvider closeLabel={t('common.close')} regionLabel={t('common.notifications')}>
          <RouterProvider router={router} />
        </ToastProvider>
      </ApiProvider>
    </QueryClientProvider>
  )
}
