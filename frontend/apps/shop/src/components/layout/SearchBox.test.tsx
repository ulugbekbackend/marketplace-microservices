import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { json, renderWithApi } from '../../test/renderApp'
import { SearchBox } from './SearchBox'

const suggestions = [
  { id: 'p1', slug: 'basic-201-futbolka', title: 'Basic 201 futbolka' },
  { id: 'p2', slug: 'urban-302-futbolka', title: 'Urban 302 futbolka' },
  { id: 'p3', slug: 'oqtepa-400-futbolka', title: 'Oqtepa 400 futbolka' },
]

const routes = [
  { path: '/', element: <SearchBox /> },
  { path: '/p/:slug', element: <SearchBox /> },
  { path: '/catalog', element: <SearchBox /> },
]

function setup() {
  const view = renderWithApi(
    routes,
    {
      'GET /api/search/suggest': (_body, url) =>
        json(200, { items: (url.searchParams.get('q') ?? '').length >= 2 ? suggestions : [] }),
    },
    '/',
  )
  const suggestCalls = () =>
    view
      .callsTo('GET', '/api/search/suggest')
      .map(([input]) => new URL(String(input)).searchParams.get('q'))
  return { ...view, suggestCalls }
}

describe('SearchBox autocomplete', () => {
  it('debounces typing and exposes the suggestions as a listbox', async () => {
    const u = userEvent.setup()
    const { suggestCalls } = setup()
    const input = screen.getByRole('combobox', { name: 'Mahsulot qidirish' })
    expect(input).toHaveAttribute('aria-expanded', 'false')

    await u.type(input, 'f')
    await u.type(input, 'ut')
    const listbox = await screen.findByRole('listbox', { name: 'Takliflar' })
    expect(within(listbox).getAllByRole('option')).toHaveLength(3)
    expect(input).toHaveAttribute('aria-expanded', 'true')
    // one request for the settled value, none for the single letter
    expect(suggestCalls()).toEqual(['fut'])
    expect(screen.getByRole('status')).toHaveTextContent('3 ta taklif')
  })

  it('moves with the arrow keys and opens the picked product on Enter', async () => {
    const u = userEvent.setup()
    const { router } = setup()
    const input = screen.getByRole('combobox')
    await u.type(input, 'fut')
    await screen.findByRole('listbox')

    await u.keyboard('{ArrowDown}')
    const options = screen.getAllByRole('option')
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    expect(input).toHaveAttribute('aria-activedescendant', options[0]!.id)

    await u.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}')
    // wraps around to the first option
    expect(options[0]).toHaveAttribute('aria-selected', 'true')
    await u.keyboard('{ArrowUp}')
    expect(options[2]).toHaveAttribute('aria-selected', 'true')

    await u.keyboard('{Enter}')
    await waitFor(() => expect(router.state.location.pathname).toBe('/p/oqtepa-400-futbolka'))
    expect(screen.getByRole('combobox')).toHaveValue('')
  })

  it('searches the catalog on Enter without an active option', async () => {
    const u = userEvent.setup()
    const { router } = setup()
    await u.type(screen.getByRole('combobox'), 'футболка{Enter}')
    await waitFor(() => expect(router.state.location.pathname).toBe('/catalog'))
    expect(new URLSearchParams(router.state.location.search).get('q')).toBe('футболка')
  })

  it('closes on Escape, clears on a second Escape, and picks with the mouse', async () => {
    const u = userEvent.setup()
    const { router } = setup()
    const input = screen.getByRole('combobox')
    await u.type(input, 'fut')
    await screen.findByRole('listbox')

    await u.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(input).toHaveValue('fut')
    await u.keyboard('{Escape}')
    expect(input).toHaveValue('')

    await u.type(input, 'urb')
    await u.click(await screen.findByRole('option', { name: 'Urban 302 futbolka' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/p/urban-302-futbolka'))
  })
})
