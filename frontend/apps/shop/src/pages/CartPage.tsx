import {
  useCart,
  useClearCart,
  useRemoveCartItem,
  useSession,
  useUpdateCartItem,
  type Cart,
  type CartGroup,
  type CartItem,
} from '@bozorcha/api-client'
import {
  Badge,
  Button,
  Card,
  cn,
  Dialog,
  EmptyState,
  formatPrice,
  QtyStepper,
  Skeleton,
  useToast,
} from '@bozorcha/ui'
import {
  ArrowRight,
  CircleAlert,
  ImageOff,
  Info,
  ShoppingCart,
  Store,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { QueryError } from '../components/QueryError'
import { cartErrorMessage } from '../lib/cartErrors'

/** Per-line quantity limit of the cart service. */
const MAX_QTY = 99
const CHECKOUT_PATH = '/checkout'

export function CartPage() {
  const { t } = useTranslation()
  const cart = useCart()

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${t('cart.title')} | ${t('common.brand')}`}</title>
      {cart.isPending ? (
        <CartSkeleton />
      ) : cart.isError ? (
        <>
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
            {t('cart.title')}
          </h1>
          <QueryError
            error={cart.error}
            onRetry={() => void cart.refetch()}
            retrying={cart.isRefetching}
          />
        </>
      ) : cart.data.groups.length === 0 ? (
        <EmptyCart cart={cart.data} />
      ) : (
        <CartView cart={cart.data} />
      )}
    </div>
  )
}

function CartView({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  const [confirmClear, setConfirmClear] = useState(false)

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="flex items-baseline gap-3">
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
            {t('cart.title')}
          </h1>
          <span className="text-sm text-text-muted tabular">
            {t('cart.itemsCount', { count: cart.items_count })}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 text-danger-ink hover:bg-danger-soft sm:ml-0 sm:-mr-3"
          leadingIcon={<Trash2 aria-hidden="true" size={16} strokeWidth={1.75} />}
          onClick={() => setConfirmClear(true)}
        >
          {t('cart.clear')}
        </Button>
      </div>

      <CartNotices cart={cart} />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-4">
          {cart.groups.map((group) => (
            <ShopGroup key={group.seller_id} group={group} />
          ))}
        </div>
        <CartSummary cart={cart} />
      </div>

      <ClearCartDialog open={confirmClear} onClose={() => setConfirmClear(false)} />
    </>
  )
}

function Notice({
  tone,
  icon,
  children,
}: {
  tone: 'info' | 'accent' | 'danger'
  icon: ReactNode
  children: ReactNode
}) {
  const tones = {
    info: 'bg-info-soft text-info-ink',
    accent: 'bg-accent-soft text-accent-ink',
    danger: 'bg-danger-soft text-danger-ink',
  } as const
  return (
    <div className={cn('flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-sm', tones[tone])}>
      <span aria-hidden="true" className="mt-px shrink-0">
        {icon}
      </span>
      <p>{children}</p>
    </div>
  )
}

function CartNotices({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  if (cart.removed.length === 0 && !cart.has_price_changes && !cart.has_unavailable) return null
  return (
    <div className="flex flex-col gap-2" role="status">
      {cart.removed.length > 0 && (
        <Notice tone="info" icon={<Info size={18} strokeWidth={1.75} />}>
          {t('cart.removedNotice', { count: cart.removed.length })}
        </Notice>
      )}
      {cart.has_price_changes && (
        <Notice tone="accent" icon={<TriangleAlert size={18} strokeWidth={1.75} />}>
          {t('cart.priceNotice')}
        </Notice>
      )}
      {cart.has_unavailable && (
        <Notice tone="danger" icon={<CircleAlert size={18} strokeWidth={1.75} />}>
          {t('cart.unavailableNotice')}
        </Notice>
      )}
    </div>
  )
}

function ShopGroup({ group }: { group: CartGroup }) {
  const { t } = useTranslation()
  const headingId = useId()
  return (
    <section aria-labelledby={headingId}>
      <Card padding="none" className="overflow-hidden dark:shadow-none">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-border bg-surface-2/60 px-4 py-3 sm:px-5">
          <h2
            id={headingId}
            className="flex min-w-0 items-center gap-2 font-heading text-base font-bold text-text"
          >
            <Store aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0" />
            <span className="truncate">{group.shop_name}</span>
          </h2>
          <p className="text-sm text-text-muted tabular">
            {t('cart.subtotal')}:{' '}
            <span className="font-semibold text-text">{formatPrice(group.subtotal_tiyin)}</span>
          </p>
        </div>
        <ul className="divide-y divide-border">
          {group.items.map((item) => (
            <CartLine key={item.variant_id} item={item} />
          ))}
        </ul>
      </Card>
    </section>
  )
}

function CartLine({ item }: { item: CartItem }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const update = useUpdateCartItem()
  const remove = useRemoveCartItem()
  // The quantity the user picked while the server call is in flight (optimistic display).
  const [draftQty, setDraftQty] = useState<number | null>(null)
  const qty = draftQty ?? item.qty
  const soldOut = item.available_qty <= 0
  const short = !item.available && !soldOut && item.available_qty < item.qty
  const maxQty = Math.max(1, Math.min(MAX_QTY, item.available_qty))
  const lineTotal = draftQty === null ? item.line_total_tiyin : item.price_tiyin * draftQty
  const productHref = `/p/${item.product_slug}`
  const attributes = item.attributes.map((a) => `${a.name}: ${a.value}`).join(', ')

  const onQty = (value: number) => {
    setDraftQty(value)
    // Only the latest call's callbacks run, so the draft clears once the last change lands.
    update.mutate(
      { variantId: item.variant_id, qty: value },
      {
        onSettled: () => setDraftQty(null),
        onError: (error) => toast({ title: cartErrorMessage(t, error), tone: 'danger' }),
      },
    )
  }

  const onRemove = () =>
    remove.mutate(
      { variantId: item.variant_id },
      { onError: (error) => toast({ title: cartErrorMessage(t, error), tone: 'danger' }) },
    )

  return (
    <li
      className={cn(
        'grid grid-cols-[4.5rem_minmax(0,1fr)] gap-x-3 gap-y-3 p-4 sm:grid-cols-[6rem_minmax(0,1fr)] sm:gap-x-4 sm:px-5',
        remove.isPending && 'opacity-50',
      )}
      aria-busy={remove.isPending || undefined}
      data-testid="cart-line"
    >
      <Link
        to={productHref}
        tabIndex={-1}
        aria-hidden="true"
        className={cn(
          'aspect-square overflow-hidden rounded-lg border border-border bg-surface-2 sm:row-span-2',
          !item.available && 'opacity-60 grayscale',
        )}
      >
        {item.image_url ? (
          <img src={item.image_url} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <span className="grid size-full place-items-center text-text-muted">
            <ImageOff size={20} strokeWidth={1.75} />
          </span>
        )}
      </Link>

      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <Link
            to={productHref}
            className="line-clamp-2 min-w-0 rounded-sm font-medium text-text [overflow-wrap:anywhere] hover:text-primary focus-ring"
          >
            {item.title}
          </Link>
          <button
            type="button"
            onClick={onRemove}
            disabled={remove.isPending}
            aria-label={t('cart.removeItem', { title: item.title })}
            title={t('cart.remove')}
            className="-mt-2 -mr-2 grid size-10 shrink-0 place-items-center rounded-lg text-text-muted transition-colors duration-150 ease-out hover:bg-danger-soft hover:text-danger-ink focus-ring disabled:opacity-50"
          >
            <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
          </button>
        </div>
        {attributes && <p className="text-sm text-text-muted">{attributes}</p>}
        <UnitPrice item={item} />
        {(soldOut || short || item.price_changed) && (
          <div className="flex flex-wrap gap-1.5">
            {soldOut && (
              <Badge tone="danger" dot>
                {t('cart.unavailable')}
              </Badge>
            )}
            {short && (
              <Badge tone="danger" dot className="tabular">
                {t('cart.onlyLeft', { count: item.available_qty })}
              </Badge>
            )}
            {!soldOut && !item.available && !short && (
              <Badge tone="danger" dot>
                {t('cart.unavailable')}
              </Badge>
            )}
            {item.price_changed && <Badge tone="accent">{t('cart.priceChanged')}</Badge>}
          </div>
        )}
      </div>

      <div className="col-span-2 flex flex-wrap items-center justify-between gap-3 sm:col-span-1 sm:col-start-2">
        <QtyStepper
          value={qty}
          onChange={onQty}
          max={maxQty}
          disabled={soldOut || remove.isPending}
          labels={{
            group: t('cart.quantityOf', { title: item.title }),
            decrease: t('product.decrease'),
            increase: t('product.increase'),
          }}
        />
        <p
          className={cn(
            'font-heading text-lg font-extrabold tabular',
            item.available ? 'text-text' : 'text-text-muted line-through',
          )}
          data-testid="line-total"
        >
          {formatPrice(lineTotal)}
        </p>
      </div>
    </li>
  )
}

function UnitPrice({ item }: { item: CartItem }) {
  const { t } = useTranslation()
  if (item.price_changed && item.previous_price_tiyin !== null) {
    return (
      <p className="flex flex-wrap items-center gap-1.5 text-sm tabular" data-testid="price-change">
        <s className="text-text-muted">
          <span className="sr-only">{t('cart.oldPrice')}: </span>
          {formatPrice(item.previous_price_tiyin)}
        </s>
        <ArrowRight aria-hidden="true" size={14} strokeWidth={1.75} className="text-text-muted" />
        <span className="font-semibold text-accent-ink">
          <span className="sr-only">{t('cart.newPrice')}: </span>
          {formatPrice(item.price_tiyin)}
        </span>
      </p>
    )
  }
  return (
    <p className="text-sm text-text-muted tabular">
      {t('cart.unitPrice', { price: formatPrice(item.price_tiyin) })}
    </p>
  )
}

function CartSummary({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  const { isAuthenticated } = useSession()
  const navigate = useNavigate()
  const headingId = useId()
  const blockedId = useId()
  const blocked = cart.has_unavailable

  const onCheckout = () =>
    navigate(isAuthenticated ? CHECKOUT_PATH : `/login?next=${encodeURIComponent(CHECKOUT_PATH)}`)

  return (
    <aside
      aria-labelledby={headingId}
      // Below lg the summary stays pinned to the bottom of the screen while the list scrolls.
      className="sticky bottom-0 z-10 -mx-4 sm:-mx-6 lg:top-36 lg:bottom-auto lg:mx-0"
    >
      <div className="flex flex-col gap-3 border-t border-border bg-surface px-4 pt-3 pb-4 shadow-[0_-2px_8px_rgb(0_0_0/0.06)] sm:px-6 lg:gap-4 lg:rounded-xl lg:border lg:p-5 lg:shadow-soft dark:shadow-none">
        <h2 id={headingId} className="font-heading text-lg font-bold text-text max-lg:sr-only">
          {t('cart.summary')}
        </h2>
        <dl className="flex flex-col gap-2 text-sm tabular">
          <div className="hidden justify-between gap-4 text-text-muted lg:flex">
            <dt>{t('cart.items', { count: cart.items_count })}</dt>
            <dd>{formatPrice(cart.total_tiyin)}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-4 lg:border-t lg:border-dashed lg:border-border lg:pt-3">
            <dt className="font-semibold text-text">{t('cart.total')}</dt>
            <dd
              className="font-heading text-xl font-extrabold text-accent-ink lg:text-2xl"
              data-testid="cart-total"
            >
              {formatPrice(cart.total_tiyin)}
            </dd>
          </div>
        </dl>
        {blocked && (
          <p id={blockedId} className="text-sm text-danger-ink">
            {t('cart.checkoutBlocked')}
          </p>
        )}
        <Button
          size="lg"
          fullWidth
          disabled={blocked}
          aria-describedby={blocked ? blockedId : undefined}
          onClick={onCheckout}
        >
          {t('cart.checkout')}
        </Button>
        {!isAuthenticated && !blocked && (
          <p className="hidden text-center text-xs text-text-muted lg:block">
            {t('cart.checkoutLoginHint')}
          </p>
        )}
      </div>
    </aside>
  )
}

function ClearCartDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const clear = useClearCart()
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t('cart.clearTitle')}
      description={t('cart.clearDescription')}
      closeLabel={t('common.close')}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('cart.cancel')}
          </Button>
          <Button
            variant="danger"
            loading={clear.isPending}
            onClick={() =>
              clear.mutate(undefined, {
                onSuccess: () => {
                  onClose()
                  toast({ title: t('cart.cleared'), tone: 'success' })
                },
                onError: (error) => toast({ title: cartErrorMessage(t, error), tone: 'danger' }),
              })
            }
          >
            {t('cart.clearConfirm')}
          </Button>
        </>
      }
    />
  )
}

function EmptyCart({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  return (
    <>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
        {t('cart.title')}
      </h1>
      <CartNotices cart={cart} />
      <EmptyState
        className="py-14"
        icon={<ShoppingCart size={22} strokeWidth={1.75} />}
        title={t('cart.empty')}
        description={t('cart.emptyHint')}
        action={
          <Link
            to="/catalog"
            className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
          >
            {t('cart.toCatalog')}
          </Link>
        }
      />
    </>
  )
}

function CartSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="flex flex-col gap-5"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <Skeleton className="h-9 w-48" />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-8">
        <div className="flex flex-col gap-4">
          {Array.from({ length: 2 }, (_, group) => (
            <div key={group} className="rounded-xl border border-border bg-surface">
              <div className="border-b border-border px-4 py-3 sm:px-5">
                <Skeleton className="h-5 w-40" />
              </div>
              {Array.from({ length: 2 }, (_, line) => (
                <div key={line} className="flex gap-3 p-4 sm:gap-4 sm:px-5">
                  <Skeleton className="size-18 shrink-0 rounded-lg sm:size-24" />
                  <div className="flex flex-1 flex-col gap-2">
                    <Skeleton className="h-4 w-full max-w-72" />
                    <Skeleton className="h-4 w-32" />
                    <div className="mt-2 flex justify-between">
                      <Skeleton className="h-11 w-30" />
                      <Skeleton className="h-6 w-24" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
        <Skeleton className="hidden h-52 rounded-xl lg:block" />
      </div>
    </div>
  )
}
