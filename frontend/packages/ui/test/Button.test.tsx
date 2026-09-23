import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from '../src/components/Button'

describe('Button', () => {
  it('is a type=button by default and handles clicks', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Saqlash</Button>)
    const button = screen.getByRole('button', { name: 'Saqlash' })
    expect(button).toHaveAttribute('type', 'button')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('loading disables clicks, marks busy and keeps the label for width', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Yuborish
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Yuborish' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('aria-disabled stays focusable and clickable', async () => {
    const onClick = vi.fn()
    render(
      <Button aria-disabled="true" onClick={onClick}>
        Savatchaga
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Savatchaga' })
    expect(button).not.toBeDisabled()
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('forwards ref and className', () => {
    const ref = createRef<HTMLButtonElement>()
    render(
      <Button ref={ref} className="custom" variant="danger">
        O'chirish
      </Button>,
    )
    expect(ref.current).toBeInstanceOf(HTMLButtonElement)
    expect(ref.current).toHaveClass('custom', 'bg-danger')
  })
})
