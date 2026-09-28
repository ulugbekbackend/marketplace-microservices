import { useChangeSubOrderStatus, type SellerSubOrderDetail } from '@bozorcha/api-client'
import { Button, Dialog, Input, Textarea, useToast } from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { Check, PackageCheck, Truck, X } from 'lucide-react'
import { useId, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import {
  ACTION_TARGET,
  availableActions,
  hasFieldError,
  isConflict,
  isOrderActive,
  REASON_MAX,
  statusErrorKey,
  TRACKING_MAX,
  type SubOrderAction,
} from '../lib/orders'

const trackingSchema = z.object({
  tracking: z.string().trim().min(1, 'trackingRequired').max(TRACKING_MAX, 'trackingTooLong'),
})
const reasonSchema = z.object({
  reason: z.string().trim().min(1, 'reasonRequired').max(REASON_MAX, 'reasonTooLong'),
})
type TrackingForm = z.infer<typeof trackingSchema>
type ReasonForm = z.infer<typeof reasonSchema>

const SUCCESS = {
  accept: 'order.accepted',
  ship: 'order.shipped',
  deliver: 'order.delivered',
  cancel: 'order.cancelled',
} as const

type Extra = { tracking_number?: string; reason?: string }

/**
 * The buttons a seller may press for the sub-order's current status, with confirmation dialogs
 * for shipping (tracking number), delivery and cancellation (reason).
 */
export function StatusActions({ order }: { order: SellerSubOrderDetail }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const change = useChangeSubOrderStatus()
  const [dialog, setDialog] = useState<Exclude<SubOrderAction, 'accept'> | null>(null)
  const [pending, setPending] = useState<SubOrderAction | null>(null)
  const actions = isOrderActive(order.order_status) ? availableActions(order.status) : []
  if (actions.length === 0) return null

  const run = (action: SubOrderAction, extra: Extra = {}, onFieldError?: () => void) => {
    setPending(action)
    change.mutate(
      { subOrderId: order.id, body: { status: ACTION_TARGET[action], ...extra } },
      {
        onSuccess: () => {
          setDialog(null)
          toast({ title: t(SUCCESS[action]), tone: 'success' })
        },
        onError: (error) => {
          const field = action === 'ship' ? 'tracking_number' : 'reason'
          if (onFieldError && hasFieldError(error, field)) {
            onFieldError()
            return
          }
          if (isConflict(error)) setDialog(null)
          toast({ title: t(statusErrorKey(error)), tone: 'danger' })
        },
        onSettled: () => setPending(null),
      },
    )
  }

  const busy = change.isPending
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t('order.actions')}>
      {actions.includes('accept') && (
        <Button
          onClick={() => run('accept')}
          loading={pending === 'accept'}
          disabled={busy && pending !== 'accept'}
          leadingIcon={<Check aria-hidden="true" size={18} strokeWidth={2} />}
        >
          {t('order.accept')}
        </Button>
      )}
      {actions.includes('ship') && (
        <Button
          onClick={() => setDialog('ship')}
          disabled={busy}
          leadingIcon={<Truck aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('order.ship')}
        </Button>
      )}
      {actions.includes('deliver') && (
        <Button
          onClick={() => setDialog('deliver')}
          disabled={busy}
          leadingIcon={<PackageCheck aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('order.deliver')}
        </Button>
      )}
      {actions.includes('cancel') && (
        <Button
          variant="secondary"
          onClick={() => setDialog('cancel')}
          disabled={busy}
          leadingIcon={<X aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('order.cancel')}
        </Button>
      )}

      <ShipDialog
        open={dialog === 'ship'}
        onClose={() => setDialog(null)}
        loading={pending === 'ship'}
        onSubmit={(tracking, onFieldError) =>
          run('ship', { tracking_number: tracking }, onFieldError)
        }
      />
      <CancelDialog
        open={dialog === 'cancel'}
        onClose={() => setDialog(null)}
        loading={pending === 'cancel'}
        onSubmit={(reason, onFieldError) => run('cancel', { reason }, onFieldError)}
      />
      <Dialog
        open={dialog === 'deliver'}
        onClose={() => setDialog(null)}
        title={t('order.deliverTitle')}
        description={t('order.deliverDescription')}
        closeLabel={t('common.close')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              {t('order.keep')}
            </Button>
            <Button onClick={() => run('deliver')} loading={pending === 'deliver'}>
              {t('order.deliverConfirm')}
            </Button>
          </>
        }
      />
    </div>
  )
}

type FormDialogProps = {
  open: boolean
  onClose: () => void
  loading: boolean
  onSubmit: (value: string, onFieldError: () => void) => void
}

function ShipDialog({ open, onClose, loading, onSubmit }: FormDialogProps) {
  const { t } = useTranslation()
  const formId = useId()
  const { register, handleSubmit, formState, setError, reset } = useForm<TrackingForm>({
    resolver: zodResolver(trackingSchema),
    defaultValues: { tracking: '' },
  })
  const close = () => {
    reset()
    onClose()
  }
  const error = formState.errors.tracking?.message as
    'trackingRequired' | 'trackingTooLong' | undefined
  return (
    <Dialog
      open={open}
      onClose={close}
      title={t('order.shipTitle')}
      description={t('order.shipDescription')}
      closeLabel={t('common.close')}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t('order.keep')}
          </Button>
          <Button type="submit" form={formId} loading={loading}>
            {t('order.shipConfirm')}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        noValidate
        onSubmit={handleSubmit(({ tracking }) =>
          onSubmit(tracking, () =>
            setError('tracking', { message: 'trackingRequired' }, { shouldFocus: true }),
          ),
        )}
      >
        <Input
          {...register('tracking')}
          label={t('order.trackingLabel')}
          hint={t('order.trackingHint')}
          error={error ? t(`order.errors.${error}`, { max: TRACKING_MAX }) : undefined}
          autoComplete="off"
          data-autofocus
          maxLength={TRACKING_MAX + 16}
          className="tabular"
        />
      </form>
    </Dialog>
  )
}

function CancelDialog({ open, onClose, loading, onSubmit }: FormDialogProps) {
  const { t } = useTranslation()
  const formId = useId()
  const { register, handleSubmit, formState, setError, reset, control } = useForm<ReasonForm>({
    resolver: zodResolver(reasonSchema),
    defaultValues: { reason: '' },
  })
  const close = () => {
    reset()
    onClose()
  }
  const length = useWatch({ control, name: 'reason' }).trim().length
  const error = formState.errors.reason?.message as 'reasonRequired' | 'reasonTooLong' | undefined
  return (
    <Dialog
      open={open}
      onClose={close}
      title={t('order.cancelTitle')}
      description={t('order.cancelDescription')}
      closeLabel={t('common.close')}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t('order.keep')}
          </Button>
          <Button type="submit" form={formId} variant="danger" loading={loading}>
            {t('order.cancelConfirm')}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-1"
        onSubmit={handleSubmit(({ reason }) =>
          onSubmit(reason, () =>
            setError('reason', { message: 'reasonRequired' }, { shouldFocus: true }),
          ),
        )}
      >
        <Textarea
          {...register('reason')}
          label={t('order.reasonLabel')}
          hint={t('order.reasonHint', { max: REASON_MAX })}
          placeholder={t('order.reasonPlaceholder')}
          error={error ? t(`order.errors.${error}`, { max: REASON_MAX }) : undefined}
          rows={3}
          data-autofocus
        />
        <p
          aria-hidden="true"
          className={
            length > REASON_MAX
              ? 'self-end text-xs text-danger-ink tabular'
              : 'self-end text-xs text-text-muted tabular'
          }
        >
          {length}/{REASON_MAX}
        </p>
      </form>
    </Dialog>
  )
}
