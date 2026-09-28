import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DataTable, type DataTableColumn } from '../src/components/DataTable'
import {
  IMAGE_MAX_BYTES,
  ImageUploader,
  validateImageFile,
  type ImageUploaderLabels,
  type UploadItem,
} from '../src/components/ImageUploader'
import { formatMmSs, useCountdown } from '../src/lib/countdown'
import { formatE164, formatNational, nationalDigits, toE164 } from '../src/lib/phone'

type Row = { id: string; title: string; stock: number }

const columns: DataTableColumn<Row>[] = [
  { id: 'title', header: 'Nomi', cell: (row) => row.title },
  { id: 'stock', header: 'Qoldiq', cell: (row) => row.stock, align: 'end' },
]

const rows: Row[] = [
  { id: 'a', title: 'Choynak', stock: 4 },
  { id: 'b', title: 'Piyola', stock: 0 },
]

describe('DataTable', () => {
  it('renders a captioned table with headers and cells', () => {
    render(<DataTable caption="Mahsulotlar" columns={columns} rows={rows} getRowId={(r) => r.id} />)
    const table = screen.getByRole('table', { name: 'Mahsulotlar' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((th) => th.textContent),
    ).toEqual(['Nomi', 'Qoldiq'])
    expect(within(table).getByRole('cell', { name: 'Piyola' })).toBeInTheDocument()
  })

  it('shows skeleton rows while loading and the empty node when there are no rows', () => {
    const { rerender, container } = render(
      <DataTable caption="T" columns={columns} rows={undefined} loading getRowId={(r) => r.id} />,
    )
    expect(screen.getByRole('table')).toHaveAttribute('aria-busy', 'true')
    expect(container.querySelectorAll('[data-skeleton]').length).toBeGreaterThan(0)
    rerender(
      <DataTable
        caption="T"
        columns={columns}
        rows={[]}
        getRowId={(r) => r.id}
        empty={<p>Hali mahsulot yo'q</p>}
      />,
    )
    expect(screen.getByText("Hali mahsulot yo'q")).toBeInTheDocument()
  })

  it('expands rows with an accessible toggle', async () => {
    const user = userEvent.setup()
    function Harness() {
      const [open, setOpen] = useState<Set<string>>(new Set())
      return (
        <DataTable
          caption="T"
          columns={columns}
          rows={rows}
          getRowId={(r) => r.id}
          expandedIds={open}
          onToggleExpanded={(id) =>
            setOpen((prev) => {
              const next = new Set(prev)
              if (next.has(id)) next.delete(id)
              else next.add(id)
              return next
            })
          }
          expandLabel={(row) => `Variantlar: ${row.title}`}
          renderExpanded={(row) => <p>{row.title} variantlari</p>}
        />
      )
    }
    render(<Harness />)
    const toggle = screen.getByRole('button', { name: 'Variantlar: Choynak' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const panel = screen.getByText('Choynak variantlari').closest('tr')!
    expect(toggle).toHaveAttribute('aria-controls', panel.id)
    await user.click(toggle)
    expect(screen.queryByText('Choynak variantlari')).not.toBeInTheDocument()
  })
})

const labels: ImageUploaderLabels = {
  title: 'Rasmlarni shu yerga tashlang',
  hint: 'JPG, PNG yoki WEBP, 10 MB gacha',
  browse: 'Fayl tanlash',
  dropHere: "Qo'yib yuboring",
  list: 'Rasmlar',
  uploading: (p) => `Yuklanmoqda ${p}%`,
  processing: 'Qayta ishlanmoqda',
  ready: 'Tayyor',
  failed: 'Xato',
  retry: 'Qayta',
}

const file = (name: string, type: string, size = 1024) => {
  const f = new File(['x'], name, { type })
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('ImageUploader', () => {
  it('validates type and size', () => {
    expect(validateImageFile(file('a.png', 'image/png'))).toBeNull()
    expect(validateImageFile(file('a.gif', 'image/gif'))).toBe('type')
    expect(validateImageFile(file('a.jpg', 'image/jpeg', IMAGE_MAX_BYTES + 1))).toBe('size')
    expect(validateImageFile(file('a.jpg', 'image/jpeg', IMAGE_MAX_BYTES))).toBeNull()
  })

  it('passes valid files on and reports rejected ones (picker and drop)', () => {
    const onFiles = vi.fn()
    const onReject = vi.fn()
    render(<ImageUploader items={[]} onFiles={onFiles} onReject={onReject} labels={labels} />)
    const good = file('a.webp', 'image/webp')
    const big = file('b.png', 'image/png', IMAGE_MAX_BYTES + 5)
    const pdf = file('c.pdf', 'application/pdf')
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [good, big, pdf] } })
    expect(onFiles).toHaveBeenCalledWith([good])
    expect(onReject).toHaveBeenCalledWith([
      { file: big, reason: 'size' },
      { file: pdf, reason: 'type' },
    ])

    const zone = screen.getByTestId('image-dropzone')
    fireEvent.dragOver(zone, { dataTransfer: { files: [], dropEffect: 'none' } })
    expect(screen.getByText("Qo'yib yuboring")).toBeInTheDocument()
    fireEvent.drop(zone, { dataTransfer: { files: [good] } })
    expect(onFiles).toHaveBeenLastCalledWith([good])
    expect(screen.getByText('Rasmlarni shu yerga tashlang')).toBeInTheDocument()
  })

  it('ignores files while disabled and explains why', () => {
    const onFiles = vi.fn()
    render(
      <ImageUploader
        items={[]}
        onFiles={onFiles}
        labels={labels}
        disabled
        disabledHint="Avval mahsulotni saqlang"
      />,
    )
    expect(screen.getByText('Avval mahsulotni saqlang')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fayl tanlash' })).toBeDisabled()
    fireEvent.drop(screen.getByTestId('image-dropzone'), {
      dataTransfer: { files: [file('a.png', 'image/png')] },
    })
    expect(onFiles).not.toHaveBeenCalled()
  })

  it('shows progress, processing, failure with retry, and ready tiles', async () => {
    const onRetry = vi.fn()
    const items: UploadItem[] = [
      { id: '1', name: 'a.png', previewUrl: 'blob:a', status: 'uploading', progress: 0.42 },
      { id: '2', name: 'b.png', previewUrl: 'blob:b', status: 'processing' },
      { id: '3', name: 'c.png', previewUrl: null, status: 'failed', error: 'Tarmoq xatosi' },
      { id: '4', name: 'd.png', previewUrl: 'https://img/d.webp', status: 'ready' },
    ]
    render(<ImageUploader items={items} onFiles={vi.fn()} onRetry={onRetry} labels={labels} />)
    const list = screen.getByRole('list', { name: 'Rasmlar' })
    expect(within(list).getByRole('progressbar', { name: 'a.png' })).toHaveAttribute(
      'aria-valuenow',
      '42',
    )
    expect(within(list).getByText('Yuklanmoqda 42%')).toBeInTheDocument()
    expect(within(list).getByText('Qayta ishlanmoqda')).toBeInTheDocument()
    expect(within(list).getByText('Tarmoq xatosi')).toBeInTheDocument()
    expect(within(list).getByRole('img', { name: 'd.png' })).toHaveAttribute(
      'src',
      'https://img/d.webp',
    )
    await userEvent.setup().click(within(list).getByRole('button', { name: 'Qayta' }))
    expect(onRetry).toHaveBeenCalledWith('3')
  })
})

describe('phone helpers', () => {
  it('formats and normalises Uzbek numbers', () => {
    expect(formatNational('901')).toBe('90 1')
    expect(nationalDigits('+998 90 123-45-67')).toBe('901234567')
    expect(toE164('90 123 45 67')).toBe('+998901234567')
    expect(formatE164('+998901234567')).toBe('+998 90 123 45 67')
  })
})

describe('countdown', () => {
  afterEach(() => vi.useRealTimers())

  it('formats mm:ss and ticks down to zero', () => {
    expect(formatMmSs(75)).toBe('01:15')
    vi.useFakeTimers()
    const deadline = Date.now() + 2000
    const { result } = renderHook(() => useCountdown(deadline))
    expect(result.current).toBe(2)
    act(() => void vi.advanceTimersByTime(2000))
    expect(result.current).toBe(0)
  })
})

describe('Textarea', () => {
  it('labels the field and links the error message', async () => {
    const { Textarea } = await import('../src/components/Textarea')
    render(<Textarea label="Tavsif" error="Juda uzun" defaultValue="Matn" />)
    const field = screen.getByLabelText('Tavsif')
    expect(field.tagName).toBe('TEXTAREA')
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(field).toHaveAccessibleDescription('Juda uzun')
  })
})
