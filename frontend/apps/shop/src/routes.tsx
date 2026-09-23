import { createBrowserRouter, type RouteObject } from 'react-router'
import { AppShell } from './components/layout/AppShell'
import { HomePage } from './pages/HomePage'
import { NotFoundPage, RouteErrorPage } from './pages/NotFoundPage'

// Home is in the main bundle; other pages load on first visit.
export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      {
        path: 'catalog/:categorySlug?',
        lazy: async () => ({ Component: (await import('./pages/CatalogPage')).CatalogPage }),
      },
      {
        path: 'p/:slug',
        lazy: async () => ({ Component: (await import('./pages/ProductPage')).ProductPage }),
      },
      {
        path: 'shop/:slug',
        lazy: async () => ({ Component: (await import('./pages/ShopPage')).ShopPage }),
      },
      {
        path: 'login',
        lazy: async () => ({ Component: (await import('./pages/LoginPage')).LoginPage }),
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
