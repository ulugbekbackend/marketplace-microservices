import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ORDER_STATUS_TONE, OrderStatusBadge } from '../src/components/Badge'
import { orderStatusTimelineTone, Timeline } from '../src/components/Timeline'

describe('Timeline', () => {
  const items = [
    { id: 'a', title: 'Yangi', time: '27.09.2026, 10:00', dateTime: '2026-09-27T05:00:00Z' },
    { id: 'b', title: 'Qabul qilindi', description: 'Ertaga jo‘natiladi', tone: 'info' as const },
  ]

  it('renders a named list with the last event as the current step', () => {
    render(<Timeline label="Holat tarixi" items={items} />)
    const list = screen.getByRole('list', { name: 'Holat tarixi' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).not.toHaveAttribute('aria-current')
    expect(rows[1]).toHaveAttribute('aria-current', 'step')
    expect(within(rows[1]!).getByText('Ertaga jo‘natiladi')).toBeInTheDocument()
    const time = within(rows[0]!).getByText('27.09.2026, 10:00')
    expect(time.tagName).toBe('TIME')
    expect(time).toHaveAttribute('dateTime', '2026-09-27T05:00:00Z')
  })

  it('shows upcoming steps after the current one without marking them current', () => {
    render(
      <Timeline
        label="Holat tarixi"
        items={items}
        upcoming={[
          { id: 'c', title: "Jo'natiladi" },
          { id: 'd', title: 'Yetkaziladi' },
        ]}
      />,
    )
    const rows = screen.getAllByRole('listitem')
    expect(rows.map((row) => row.dataset.state)).toEqual([
      'done',
      'current',
      'upcoming',
      'upcoming',
    ])
    expect(rows.filter((row) => row.getAttribute('aria-current') === 'step')).toHaveLength(1)
  })

  it('forwards className and extra props to the list', () => {
    render(<Timeline label="Tarix" items={items} className="mt-2" data-testid="tl" />)
    expect(screen.getByTestId('tl')).toHaveClass('mt-2')
  })

  it('maps statuses to the same colour family as their badges', () => {
    expect(orderStatusTimelineTone('SHIPPED')).toBe('purple')
    expect(orderStatusTimelineTone('CANCELLED_BY_SELLER')).toBe('danger')
    expect(orderStatusTimelineTone('EXPIRED')).toBe('neutral')
    expect(orderStatusTimelineTone('DELIVERED')).toBe('primary')
  })
})

describe('sub-order statuses in the shared mapping', () => {
  it('covers every sub-order status with the design system colours', () => {
    expect(ORDER_STATUS_TONE.NEW).toBe('neutral')
    expect(ORDER_STATUS_TONE.ACCEPTED).toBe('info')
    expect(ORDER_STATUS_TONE.SHIPPED).toBe('purple')
    expect(ORDER_STATUS_TONE.DELIVERED).toBe('primary')
    expect(ORDER_STATUS_TONE.CANCELLED_BY_SELLER).toBe('danger')
  })

  it('renders a NEW badge with its localized label', () => {
    render(<OrderStatusBadge status="NEW">Yangi</OrderStatusBadge>)
    const badge = screen.getByText('Yangi')
    expect(badge).toHaveAttribute('data-status', 'NEW')
    expect(badge).toHaveClass('bg-surface-2')
  })
})
