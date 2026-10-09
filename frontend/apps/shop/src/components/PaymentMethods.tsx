import { isApiError, useInitPayment, useMockPayment, type Order } from '@bozorcha/api-client'
import { Button, cn, useToast } from '@bozorcha/ui'
import { FlaskConical, Wallet } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { paymentErrorMessage } from '../lib/paymentErrors'
import { leaveTo } from '../lib/redirect'
import { MOCK_PAYMENT_ENABLED, paymentResultPath, type PaymentMethod } from '../lib/orders'

type MethodOption = { id: PaymentMethod; test?: boolean }

const PROVIDERS: MethodOption[] = [{ id: 'payme' }, { id: 'click' }]

/**
 * How the customer pays a RESERVED order. Payme and Click go through the provider's checkout
 * (or straight to the result page while no checkout is configured); the test method pays at
 * once through the payment service and is offered only where mock payments are enabled.
 */
export function PaymentMethods({ order, onRejected }: { order: Order; onRejected: () => void }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const init = useInitPayment()
  const mock = useMockPayment()
  const [mockAvailable, setMockAvailable] = useState(MOCK_PAYMENT_ENABLED)
  const [method, setMethod] = useState<PaymentMethod>('payme')
  const [leaving, setLeaving] = useState(false)
  const name = useId()

  const options = mockAvailable ? [...PROVIDERS, { id: 'mock', test: true } as const] : PROVIDERS
  const busy = init.isPending || mock.isPending || leaving

  const fail = (error: unknown) => {
    if (isApiError(error) && error.code === 'ORDER_NOT_PAYABLE') onRejected()
    const tone = isApiError(error) && error.code === 'PAYMENT_IN_PROGRESS' ? 'info' : 'danger'
    toast({ title: paymentErrorMessage(t, error), tone })
  }

  const pay = () => {
    if (method === 'mock') {
      mock.mutate(
        { orderId: order.id },
        {
          onSuccess: () => void navigate(paymentResultPath(order.id, 'mock')),
          onError: (error) => {
            if (isApiError(error) && error.status === 404) {
              setMockAvailable(false)
              setMethod('payme')
              toast({ title: t('orders.mockDisabled'), tone: 'info' })
            } else {
              fail(error)
            }
          },
        },
      )
      return
    }
    init.mutate(
      { orderId: order.id, provider: method },
      {
        onSuccess: ({ redirect_url }) => {
          setLeaving(true)
          leaveTo(redirect_url)
        },
        onError: fail,
      },
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <fieldset className="flex flex-col gap-2" disabled={busy}>
        <legend className="mb-2 text-sm font-semibold text-text">{t('payment.method')}</legend>
        <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-3">
          {options.map((option) => (
            <MethodTile
              key={option.id}
              name={name}
              option={option}
              checked={method === option.id}
              onSelect={() => setMethod(option.id)}
            />
          ))}
        </div>
      </fieldset>
      <Button
        variant="accent"
        size="lg"
        loading={busy}
        onClick={pay}
        className="w-full sm:w-auto sm:self-start"
      >
        {t(method === 'mock' ? 'payment.payTest' : 'payment.payWith', {
          provider: t(`payment.provider.${method}`),
        })}
      </Button>
    </div>
  )
}

function MethodTile({
  name,
  option,
  checked,
  onSelect,
}: {
  name: string
  option: MethodOption
  checked: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const id = useId()
  const Icon = option.test ? FlaskConical : Wallet
  return (
    <label
      htmlFor={id}
      data-testid={`method-${option.id}`}
      className={cn(
        'flex min-h-14 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-150 ease-out has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60',
        checked
          ? 'border-primary bg-primary-soft text-text'
          : 'border-border bg-surface text-text hover:bg-surface-2',
      )}
    >
      <input
        id={id}
        type="radio"
        name={name}
        value={option.id}
        checked={checked}
        onChange={onSelect}
        className="size-4 shrink-0 accent-primary"
      />
      <Icon aria-hidden="true" size={18} strokeWidth={1.75} className="shrink-0 text-text-muted" />
      <span className="flex min-w-0 flex-col font-semibold">
        {t(`payment.provider.${option.id}`)}
        <span className="text-xs font-normal text-text-muted">
          {t(`payment.providerHint.${option.id}`)}
        </span>
      </span>
    </label>
  )
}
