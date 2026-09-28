import {
  isApiError,
  newIdempotencyKey,
  useCart,
  useCheckout,
  useMe,
  type Cart,
  type UnavailableItem,
} from '@bozorcha/api-client'
import {
  Button,
  Card,
  EmptyState,
  formatNational,
  formatPrice,
  Input,
  nationalDigits,
  Select,
  Skeleton,
  toE164,
  UZ_COUNTRY_CODE,
} from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlert, MapPin, ShoppingCart, Store } from 'lucide-react'
import { useEffect, useId, useState, type ComponentProps } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'
import { QueryError } from '../components/QueryError'
import { RequireAuth } from '../components/RequireAuth'
import { orderErrorMessage, unavailableItemsFromError } from '../lib/orderErrors'
import { REGIONS } from '../lib/regions'

const LIMITS = { full_name: 120, city: 100, street: 255, notes: 500 } as const

const tooLong = (max: number) => `tooLong:${max}`

const addressSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(1, 'fullNameRequired')
    .max(LIMITS.full_name, tooLong(LIMITS.full_name)),
  phone: z
    .string()
    .min(1, 'phoneRequired')
    .refine((value) => nationalDigits(value).length === 9, 'phoneInvalid'),
  region: z.enum(REGIONS, { error: 'regionRequired' }),
  city: z.string().trim().min(1, 'cityRequired').max(LIMITS.city, tooLong(LIMITS.city)),
  street: z.string().trim().min(1, 'streetRequired').max(LIMITS.street, tooLong(LIMITS.street)),
  notes: z.string().trim().max(LIMITS.notes, tooLong(LIMITS.notes)),
})

type AddressInput = z.input<typeof addressSchema>
type AddressForm = z.output<typeof addressSchema>

const emptyForm: AddressInput = {
  full_name: '',
  phone: '',
  region: '' as AddressInput['region'],
  city: '',
  street: '',
  notes: '',
}

export function CheckoutPage() {
  return (
    <RequireAuth>
      <Checkout />
    </RequireAuth>
  )
}

function Checkout() {
  const { t } = useTranslation()
  const cart = useCart()

  return (
    <div className="page-container flex flex-col gap-5 pt-5 sm:pt-6">
      <title>{`${t('checkout.title')} | ${t('common.brand')}`}</title>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text sm:text-3xl">
        {t('checkout.title')}
      </h1>
      {cart.isPending ? (
        <CheckoutSkeleton />
      ) : cart.isError ? (
        <QueryError
          error={cart.error}
          onRetry={() => void cart.refetch()}
          retrying={cart.isRefetching}
        />
      ) : cart.data.groups.length === 0 ? (
        <EmptyState
          className="py-14"
          icon={<ShoppingCart size={22} strokeWidth={1.75} />}
          title={t('checkout.emptyTitle')}
          description={t('checkout.emptyHint')}
          action={
            <Link
              to="/catalog"
              className="inline-flex h-11 items-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-fg hover:bg-primary-hover focus-ring"
            >
              {t('cart.toCatalog')}
            </Link>
          }
        />
      ) : (
        <CheckoutForm cart={cart.data} />
      )}
    </div>
  )
}

type SubmitProblem = { message: string; items: { title: string; item: UnavailableItem }[] }

function CheckoutForm({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const me = useMe()
  const checkout = useCheckout()
  const formId = useId()
  const errorId = useId()
  const blockedId = useId()
  // One key per checkout attempt: every retry of the same submit (a second click after a failed
  // request included) carries it, so the server can never create two orders from one attempt.
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey)
  const [problem, setProblem] = useState<SubmitProblem | null>(null)

  const { control, register, handleSubmit, formState, getFieldState, setValue } = useForm<
    AddressInput,
    unknown,
    AddressForm
  >({ resolver: zodResolver(addressSchema), defaultValues: emptyForm })

  // Prefill from the profile, without overwriting anything the user already typed.
  const profile = me.data
  useEffect(() => {
    if (!profile) return
    if (profile.full_name && !getFieldState('full_name').isDirty) {
      setValue('full_name', profile.full_name)
    }
    if (profile.phone && !getFieldState('phone').isDirty) {
      setValue('phone', formatNational(nationalDigits(profile.phone)))
    }
  }, [profile, getFieldState, setValue])

  const blocked = cart.has_unavailable

  const onSubmit = handleSubmit((values) => {
    if (blocked || checkout.isPending) return
    setProblem(null)
    // Titles are taken now: the cart is refetched after an error and may lose these lines.
    const titles = new Map(
      cart.groups.flatMap((group) => group.items.map((item) => [item.variant_id, item.title])),
    )
    checkout.mutate(
      {
        idempotencyKey,
        address: {
          full_name: values.full_name,
          phone: toE164(values.phone),
          region: t(`regions.${values.region}`),
          city: values.city,
          street: values.street,
          notes: values.notes,
        },
      },
      {
        onSuccess: (result) => navigate(`/orders/${result.order_id}`, { replace: true }),
        onError: (error) => {
          setProblem({
            message: orderErrorMessage(t, error),
            items: unavailableItemsFromError(error).map((item) => ({
              item,
              title: titles.get(item.variant_id) ?? t('checkout.unknownItem'),
            })),
          })
          // The key was already used for an order with another address: a new attempt needs a
          // new key (the message tells the user to check their orders first).
          if (isApiError(error) && error.code === 'IDEMPOTENCY_KEY_REUSED') {
            setIdempotencyKey(newIdempotencyKey())
          }
        },
      },
    )
  })

  const fieldError = (name: keyof AddressInput) => {
    const message = formState.errors[name]?.message
    if (!message) return undefined
    if (message.startsWith('tooLong:')) {
      return t('checkout.errors.tooLong', { max: Number(message.split(':')[1]) })
    }
    return t(`checkout.errors.${message as 'fullNameRequired'}`)
  }

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-8">
      <Card padding="lg" className="dark:shadow-none">
        <form
          id={formId}
          onSubmit={onSubmit}
          noValidate
          aria-labelledby={`${formId}-title`}
          className="flex flex-col gap-4"
        >
          <h2
            id={`${formId}-title`}
            className="flex items-center gap-2 font-heading text-lg font-bold text-text"
          >
            <MapPin aria-hidden="true" size={20} strokeWidth={1.75} />
            {t('checkout.addressTitle')}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={t('checkout.fullName')}
              placeholder={t('checkout.fullNamePlaceholder')}
              autoComplete="name"
              error={fieldError('full_name')}
              {...register('full_name')}
            />
            <Controller
              control={control}
              name="phone"
              render={({ field }) => (
                <Input
                  ref={field.ref}
                  name={field.name}
                  value={field.value}
                  onBlur={field.onBlur}
                  onChange={(event) => field.onChange(formatNational(event.target.value))}
                  label={t('checkout.phone')}
                  error={fieldError('phone')}
                  prefix={
                    <span className="text-base font-medium text-text tabular">
                      {UZ_COUNTRY_CODE}
                    </span>
                  }
                  className="pl-16 tabular"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel-national"
                  placeholder="90 123 45 67"
                />
              )}
            />
            <Select
              label={t('checkout.region')}
              placeholder={t('checkout.regionPlaceholder')}
              options={REGIONS.map((key) => ({ value: key, label: t(`regions.${key}`) }))}
              error={fieldError('region')}
              {...register('region')}
            />
            <Input
              label={t('checkout.city')}
              autoComplete="address-level2"
              error={fieldError('city')}
              {...register('city')}
            />
            <Input
              label={t('checkout.street')}
              placeholder={t('checkout.streetPlaceholder')}
              autoComplete="street-address"
              wrapperClassName="sm:col-span-2"
              error={fieldError('street')}
              {...register('street')}
            />
            <NotesField error={fieldError('notes')} {...register('notes')} />
          </div>
        </form>
      </Card>

      <aside
        aria-labelledby={`${formId}-summary`}
        className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-soft lg:sticky lg:top-36 dark:shadow-none"
      >
        <h2 id={`${formId}-summary`} className="font-heading text-lg font-bold text-text">
          {t('checkout.summary')}
        </h2>
        <CartLines cart={cart} />
        <div className="flex items-baseline justify-between gap-4 border-t border-dashed border-border pt-3 tabular">
          <span className="font-semibold text-text">{t('checkout.total')}</span>
          <span
            className="font-heading text-2xl font-extrabold text-accent-ink"
            data-testid="checkout-total"
          >
            {formatPrice(cart.total_tiyin)}
          </span>
        </div>

        {blocked && (
          <div
            id={blockedId}
            className="flex flex-col gap-1 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
          >
            <p className="font-semibold">{t('checkout.unavailableTitle')}</p>
            <p>{t('checkout.unavailableHint')}</p>
          </div>
        )}
        {problem && (
          <div
            id={errorId}
            role="alert"
            className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
          >
            <CircleAlert
              aria-hidden="true"
              size={18}
              strokeWidth={1.75}
              className="mt-px shrink-0"
            />
            <div className="flex min-w-0 flex-col gap-1">
              <p>{problem.message}</p>
              {problem.items.length > 0 && (
                <>
                  <p>{t('checkout.itemsProblem')}</p>
                  <ul className="list-disc pl-4">
                    {problem.items.map(({ item, title }) => (
                      <li key={item.variant_id}>
                        {title}: <ReasonText item={item} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        )}

        <Button
          type="submit"
          form={formId}
          size="lg"
          fullWidth
          loading={checkout.isPending}
          disabled={blocked}
          aria-describedby={
            [blocked && blockedId, problem && errorId].filter(Boolean).join(' ') || undefined
          }
        >
          {t('checkout.submit')}
        </Button>
        <p className="text-center text-xs text-text-muted">{t('checkout.submitHint')}</p>
        <Link
          to="/cart"
          className="self-center rounded-sm text-sm font-semibold text-primary hover:underline focus-ring"
        >
          {t('checkout.editCart')}
        </Link>
      </aside>
    </div>
  )
}

function ReasonText({ item }: { item: UnavailableItem }) {
  const { t } = useTranslation()
  if (item.reason === 'out_of_stock') {
    return item.available > 0
      ? t('checkout.itemReason.out_of_stock', { count: item.available })
      : t('checkout.itemReason.out_of_stock_none')
  }
  return t(`checkout.itemReason.${item.reason}`)
}

function NotesField({ error, ...props }: { error?: string } & ComponentProps<'textarea'>) {
  const { t } = useTranslation()
  const id = useId()
  return (
    <div className="flex flex-col gap-1.5 sm:col-span-2">
      <label htmlFor={id} className="text-sm font-medium text-text">
        {t('checkout.notes')}
      </label>
      <textarea
        id={id}
        rows={3}
        aria-invalid={error ? true : undefined}
        aria-describedby={`${id}-msg`}
        className="w-full min-w-0 resize-y rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-base text-text transition-colors duration-150 ease-out placeholder:text-text-muted focus-visible:border-primary focus-visible:bg-surface focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-primary aria-[invalid=true]:border-danger"
        {...props}
      />
      <p
        id={`${id}-msg`}
        role={error ? 'alert' : undefined}
        className={error ? 'text-sm text-danger-ink' : 'text-sm text-text-muted'}
      >
        {error ?? t('checkout.notesHint')}
      </p>
    </div>
  )
}

function CartLines({ cart }: { cart: Cart }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-4">
      {cart.groups.map((group) => (
        <section key={group.seller_id} aria-label={group.shop_name} className="flex flex-col gap-2">
          <h3 className="flex min-w-0 items-center gap-1.5 text-sm font-semibold text-text">
            <Store aria-hidden="true" size={16} strokeWidth={1.75} className="shrink-0" />
            <span className="truncate">{group.shop_name}</span>
          </h3>
          <ul className="flex flex-col gap-2">
            {group.items.map((item) => (
              <li
                key={item.variant_id}
                className="flex items-start justify-between gap-3 text-sm"
                data-testid="checkout-line"
              >
                <div className="min-w-0">
                  <p className="line-clamp-2 text-text [overflow-wrap:anywhere]">{item.title}</p>
                  <p className="text-text-muted tabular">
                    {t('checkout.itemLine', {
                      qty: item.qty,
                      price: formatPrice(item.price_tiyin),
                    })}
                  </p>
                  {!item.available && (
                    <p className="font-medium text-danger-ink">{t('cart.unavailable')}</p>
                  )}
                </div>
                <span className="shrink-0 font-semibold text-text tabular">
                  {formatPrice(item.line_total_tiyin)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function CheckoutSkeleton() {
  const { t } = useTranslation()
  return (
    <div
      className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-8"
      role="status"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-6">
        <Skeleton className="h-6 w-56" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
          <Skeleton className="h-16 sm:col-span-2" />
          <Skeleton className="h-24 sm:col-span-2" />
        </div>
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  )
}
