import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Dialog } from '../src/components/Dialog'
import { Drawer } from '../src/components/Drawer'
import { ToastProvider, useToast } from '../src/components/Toast'

function DialogHarness() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Ochish</button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Chiqish"
        description="Hisobdan chiqasizmi?"
        closeLabel="Yopish"
        footer={<button>Ha</button>}
      >
        <input aria-label="Izoh" />
      </Dialog>
    </>
  )
}

describe('Dialog', () => {
  it('opens as a labelled modal, traps focus, closes on Escape and restores focus', async () => {
    const user = userEvent.setup()
    render(<DialogHarness />)
    const trigger = screen.getByRole('button', { name: 'Ochish' })
    await user.click(trigger)

    const dialog = screen.getByRole('dialog', { name: 'Chiqish' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleDescription('Hisobdan chiqasizmi?')
    expect(document.body.style.overflow).toBe('hidden')

    // Tab order: close, input, "Ha" -> wraps back to close
    await user.tab()
    expect(screen.getByRole('button', { name: 'Yopish' })).toHaveFocus()
    await user.tab()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Ha' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Yopish' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Ha' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(document.body.style.overflow).toBe('')
  })
})

describe('Drawer', () => {
  it('closes from the scrim and the close button', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <Drawer open onClose={onClose} title="Kategoriyalar" closeLabel="Yopish">
        <a href="/catalog">Hammasi</a>
      </Drawer>,
    )
    expect(screen.getByRole('dialog', { name: 'Kategoriyalar' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yopish' }))
    await user.click(screen.getByTestId('overlay-scrim'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

function ToastTrigger() {
  const { toast } = useToast()
  return <button onClick={() => toast({ title: 'Tez orada', duration: 1000 })}>Bosish</button>
}

describe('Toast', () => {
  it('announces in a live region and auto-dismisses', async () => {
    vi.useFakeTimers()
    try {
      render(
        <ToastProvider closeLabel="Yopish" regionLabel="Bildirishnomalar">
          <ToastTrigger />
        </ToastProvider>,
      )
      act(() => screen.getByRole('button', { name: 'Bosish' }).click())
      const region = screen.getByRole('region', { name: 'Bildirishnomalar' })
      expect(region).toHaveAttribute('aria-live', 'polite')
      expect(region).toHaveTextContent('Tez orada')
      act(() => vi.advanceTimersByTime(1000))
      expect(region).not.toHaveTextContent('Tez orada')
    } finally {
      vi.useRealTimers()
    }
  })

  it('throws a helpful error outside the provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ToastTrigger />)).toThrow(/ToastProvider/)
    vi.restoreAllMocks()
  })
})
