import { createBrowserRouter, Outlet, type RouteObject } from 'react-router'
import { AppRoot } from './components/layout/AppRoot'
import { PanelLayout } from './components/layout/PanelLayout'
import { RequireAuth } from './components/RequireAuth'
import { RequireSeller } from './components/RequireSeller'
import { DashboardPage } from './pages/DashboardPage'
import { NotFoundPage, RouteErrorPage } from './pages/NotFoundPage'

/** The panel shell and dashboard are in the main bundle; other pages load on first visit. */
export const routes: RouteObject[] = [
  {
    element: <AppRoot />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        path: 'login',
        lazy: async () => ({ Component: (await import('./pages/LoginPage')).LoginPage }),
      },
      {
        element: (
          <RequireAuth>
            <Outlet />
          </RequireAuth>
        ),
        children: [
          {
            path: 'onboarding',
            lazy: async () => ({
              Component: (await import('./pages/OnboardingPage')).OnboardingPage,
            }),
          },
        ],
      },
      {
        element: (
          <RequireAuth>
            <RequireSeller>
              <PanelLayout />
            </RequireSeller>
          </RequireAuth>
        ),
        children: [
          { index: true, element: <DashboardPage /> },
          {
            path: 'products',
            lazy: async () => ({ Component: (await import('./pages/ProductsPage')).ProductsPage }),
          },
          {
            path: 'products/:productId',
            lazy: async () => ({
              Component: (await import('./pages/ProductEditorPage')).ProductEditorPage,
            }),
          },
          {
            path: 'orders',
            lazy: async () => ({ Component: (await import('./pages/OrdersPage')).OrdersPage }),
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export const router = createBrowserRouter(routes)
