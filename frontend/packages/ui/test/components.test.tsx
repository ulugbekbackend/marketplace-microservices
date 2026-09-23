import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Badge, OrderStatusBadge, ORDER_STATUS_TONE } from '../src/components/Badge'
import { Checkbox } from '../src/components/Checkbox'
import { EmptyState } from '../src/components/EmptyState'
import { Input } from '../src/components/Input'
import { Pagination, pageWindow } from '../src/components/Pagination'
import { PriceTag } from '../src/components/PriceTag'
import { ProductCard } from '../src/components/ProductCard'
import { QtyStepper } from '../src/components/QtyStepper'
import { Select } from '../src/components/Select'
import { Tabs } from '../src/components/Tabs'

const plain = (text: string | null) => (text ?? '').replaceAll(String.fromCharCode(0xa0), ' ')

describe('Badge', () => {
  it('maps order statuses to the shared colours', () => {
    expect(ORDER_STATUS_TONE.PAID).toBe('success')
    expect(ORDER_STATUS_TONE.SHIPPED).toBe('purple')
    expect(ORDER_STATUS_TONE.COMPLETED).toBe('primary')
    expect(ORDER_STATUS_TONE.REFUNDED).toBe('danger')
    expect(ORDER_STATUS_TONE.EXPIRED).toBe('muted')
    render(<OrderStatusBadge status="SHIPPED">Yo'lda</OrderStatusBadge>)
    expect(screen.getByText("Yo'lda").closest('[data-status]')).toHaveClass('bg-purple-soft')
  })

  it('falls back to the status code', () => {
    render(<OrderStatusBadge status="PENDING" />)
    expect(screen.getByText('PENDING')).toBeInTheDocument()
  })

  it('renders tones', () => {
    render(<Badge tone="danger">Xato</Badge>)
    expect(screen.getByText('Xato')).toHaveClass('text-danger-ink')
  })
})

describe('PriceTag', () => {
  it('shows price, struck old price and discount', () => {
    render(<PriceTag price={75_000_00} oldPrice={100_000_00} oldPriceLabel="Oldingi narx" />)
    expect(plain(screen.getByTestId('price').textContent)).toBe("75 000 so'm")
    expect(plain(screen.getByText(/Oldingi narx/).closest('s')!.textContent)).toBe(
      "Oldingi narx: 100 000 so'm",
    )
    expect(screen.getByText('-25%')).toBeInTheDocument()
  })
})

describe('ProductCard', () => {
  const base = {
    href: '/p/choynak',
    title: 'Chinni choynak',
    imageUrl: null,
    minPrice: 120_000_00,
    sellerName: 'Rishton sopol',
    labels: { outOfStock: 'Tugagan', from: 'dan' },
  }

  it('is a single link with title, price and seller', () => {
    render(<ProductCard {...base} inStock />)
    expect(screen.getByRole('link', { name: 'Chinni choynak' })).toHaveAttribute(
      'href',
      '/p/choynak',
    )
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.getByText('Rishton sopol')).toBeInTheDocument()
    expect(screen.queryByText('dan')).not.toBeInTheDocument()
  })

  it('marks price ranges and out-of-stock', () => {
    render(<ProductCard {...base} maxPrice={150_000_00} inStock={false} />)
    expect(screen.getByText('dan')).toBeInTheDocument()
    expect(screen.getByText('Tugagan')).toBeInTheDocument()
  })

  it('uses a custom link component', () => {
    const Custom = ({ href, children }: { href: string; children: React.ReactNode }) => (
      <a href={href} data-router="yes">
        {children}
      </a>
    )
    render(<ProductCard {...base} inStock linkAs={Custom} />)
    expect(screen.getByRole('link')).toHaveAttribute('data-router', 'yes')
  })
})

describe('Input / Select / Checkbox', () => {
  it('links label, error and aria-invalid', () => {
    render(<Input label="Telefon" error="Raqam noto'g'ri" />)
    const input = screen.getByLabelText('Telefon')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription("Raqam noto'g'ri")
  })

  it('renders select options with a label', async () => {
    const onChange = vi.fn()
    render(
      <Select
        label="Saralash"
        defaultValue="new"
        onChange={onChange}
        options={[
          { value: 'new', label: 'Yangilari' },
          { value: 'cheap', label: 'Arzonlari' },
        ]}
      />,
    )
    await userEvent.selectOptions(screen.getByLabelText('Saralash'), 'cheap')
    expect(onChange).toHaveBeenCalled()
  })

  it('toggles a checkbox via its label', async () => {
    render(<Checkbox label="Faqat mavjudlari" />)
    await userEvent.click(screen.getByText('Faqat mavjudlari'))
    expect(screen.getByRole('checkbox', { name: 'Faqat mavjudlari' })).toBeChecked()
  })
})

function Stepper() {
  const [value, setValue] = useState(1)
  return (
    <QtyStepper
      value={value}
      onChange={setValue}
      max={3}
      labels={{ group: 'Soni', decrease: 'Kamaytirish', increase: "Ko'paytirish" }}
    />
  )
}

describe('QtyStepper', () => {
  it('clamps between min and max with buttons and keys', async () => {
    const user = userEvent.setup()
    render(<Stepper />)
    const input = screen.getByRole('spinbutton', { name: 'Soni' })
    expect(screen.getByRole('button', { name: 'Kamaytirish' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: "Ko'paytirish" }))
    expect(input).toHaveValue('2')
    await user.click(input)
    await user.keyboard('{ArrowUp}{ArrowUp}')
    expect(input).toHaveAttribute('aria-valuenow', '3')
    expect(screen.getByRole('button', { name: "Ko'paytirish" })).toBeDisabled()
    await user.keyboard('{Home}')
    expect(input).toHaveValue('1')
  })

  it('clamps typed values on blur', async () => {
    const user = userEvent.setup()
    render(<Stepper />)
    const input = screen.getByRole('spinbutton')
    await user.clear(input)
    await user.type(input, '50')
    await user.tab()
    expect(input).toHaveValue('3')
  })
})

describe('Tabs', () => {
  it('switches with arrow keys and shows one panel', async () => {
    const user = userEvent.setup()
    render(
      <Tabs
        label="Mahsulot"
        items={[
          { id: 'desc', label: 'Tavsif', content: 'Tavsif matni' },
          { id: 'specs', label: 'Xususiyatlar', content: 'Xususiyatlar jadvali' },
        ]}
      />,
    )
    const first = screen.getByRole('tab', { name: 'Tavsif' })
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Tavsif matni')
    await user.click(first)
    await user.keyboard('{ArrowRight}')
    const second = screen.getByRole('tab', { name: 'Xususiyatlar' })
    expect(second).toHaveFocus()
    expect(second).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Xususiyatlar jadvali')
    expect(first).toHaveAttribute('tabindex', '-1')
  })
})

describe('Pagination', () => {
  it('computes a compact page window', () => {
    expect(pageWindow(1, 5)).toEqual([1, 2, 3, 4, 5])
    expect(pageWindow(5, 20)).toEqual([1, null, 4, 5, 6, null, 20])
    expect(pageWindow(1, 20)).toEqual([1, 2, null, 20])
    expect(pageWindow(20, 20)).toEqual([1, null, 19, 20])
  })

  it('renders links with the current page marked', () => {
    render(
      <Pagination
        page={2}
        pageCount={3}
        hrefFor={(p) => `/catalog?page=${p}`}
        labels={{
          nav: 'Sahifalar',
          previous: 'Oldingi',
          next: 'Keyingi',
          page: (p) => `${p}-sahifa`,
        }}
      />,
    )
    const nav = screen.getByRole('navigation', { name: 'Sahifalar' })
    expect(within(nav).getByText('2')).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Keyingi' })).toHaveAttribute(
      'href',
      '/catalog?page=3',
    )
    expect(within(nav).getByRole('link', { name: '1-sahifa' })).toHaveAttribute(
      'href',
      '/catalog?page=1',
    )
  })

  it('renders nothing for a single page', () => {
    const { container } = render(
      <Pagination
        page={1}
        pageCount={1}
        hrefFor={String}
        labels={{ nav: 'n', previous: 'p', next: 'x', page: String }}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('EmptyState', () => {
  it('renders a title, description and action', () => {
    render(
      <EmptyState
        title="Hech narsa topilmadi"
        description="Boshqa so'z bilan qidiring"
        action={<button>Tozalash</button>}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Hech narsa topilmadi' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tozalash' })).toBeInTheDocument()
  })
})
