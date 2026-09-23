import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { OtpInput } from '../src/components/OtpInput'

function Harness({ onComplete }: { onComplete?: (code: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <>
      <OtpInput
        value={value}
        onChange={setValue}
        onComplete={onComplete}
        label="Tasdiqlash kodi"
        cellLabel={(i, n) => `${i + 1}-raqam, jami ${n}`}
      />
      <output data-testid="value">{value}</output>
    </>
  )
}

const cells = () => screen.getAllByRole('textbox')

describe('OtpInput', () => {
  it('renders six labelled cells inside a named group', () => {
    render(<Harness />)
    expect(screen.getByRole('group', { name: 'Tasdiqlash kodi' })).toBeInTheDocument()
    expect(cells()).toHaveLength(6)
    expect(cells()[0]).toHaveAccessibleName('1-raqam, jami 6')
    expect(cells()[0]).toHaveAttribute('autocomplete', 'one-time-code')
  })

  it('auto-advances focus while typing and completes', async () => {
    const onComplete = vi.fn()
    const user = userEvent.setup()
    render(<Harness onComplete={onComplete} />)
    await user.click(cells()[0]!)
    await user.keyboard('12')
    expect(cells()[2]).toHaveFocus()
    await user.keyboard('3456')
    expect(screen.getByTestId('value')).toHaveTextContent('123456')
    expect(onComplete).toHaveBeenCalledExactlyOnceWith('123456')
  })

  it('ignores non-digits', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(cells()[0]!)
    await user.keyboard('a1b')
    expect(screen.getByTestId('value')).toHaveTextContent(/^1$/)
  })

  it('distributes a pasted code across the cells', async () => {
    const onComplete = vi.fn()
    const user = userEvent.setup()
    render(<Harness onComplete={onComplete} />)
    await user.click(cells()[0]!)
    await user.paste('Kod: 654-321')
    expect(screen.getByTestId('value')).toHaveTextContent('654321')
    expect(cells().map((c) => (c as HTMLInputElement).value)).toEqual([
      '6',
      '5',
      '4',
      '3',
      '2',
      '1',
    ])
    expect(onComplete).toHaveBeenCalledWith('654321')
  })

  it('backspace clears the current cell, then moves back', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(cells()[0]!)
    await user.keyboard('123')
    // focus is on the 4th (empty) cell: backspace removes the 3rd digit and moves there
    await user.keyboard('{Backspace}')
    expect(screen.getByTestId('value')).toHaveTextContent(/^12$/)
    expect(cells()[2]).toHaveFocus()
    await user.keyboard('{Backspace}')
    expect(screen.getByTestId('value')).toHaveTextContent(/^1$/)
    expect(cells()[1]).toHaveFocus()
  })

  it('does not allow gaps: clicking a later cell focuses the first empty one', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(cells()[4]!)
    expect(cells()[0]).toHaveFocus()
  })

  it('supports arrow key navigation', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(cells()[0]!)
    await user.keyboard('123')
    await user.keyboard('{ArrowLeft}{ArrowLeft}')
    expect(cells()[1]).toHaveFocus()
    await user.keyboard('9')
    expect(screen.getByTestId('value')).toHaveTextContent(/^193$/)
  })
})
