import {
  CLIENT_ERROR,
  isApiError,
  queryKeys,
  useApi,
  useApplySeller,
  useMe,
  useSellerApplication,
  type SellerApplication,
} from '@bozorcha/api-client'
import { Button, Card, cn, Input, Skeleton, Spinner, Textarea } from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Check, CircleAlert, Clock, RotateCw, Store, XCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'
import { z } from 'zod'
import { AuthFrame } from '../components/layout/AuthFrame'
import { QueryError } from '../components/QueryError'
import { formatDateTime } from '../lib/dates'

const SHOP_NAME_MAX = 120
const APPLICATION_DESCRIPTION_MAX = 2000

const applySchema = z.object({
  shop_name: z.string().trim().min(2, 'shopNameRequired').max(SHOP_NAME_MAX, 'shopNameTooLong'),
  inn: z.string().regex(/^\d{9}$/, 'innInvalid'),
  description: z.string().max(APPLICATION_DESCRIPTION_MAX, 'descriptionTooLong'),
})
type ApplyValues = z.infer<typeof applySchema>
type ApplyErrorKey = 'shopNameRequired' | 'shopNameTooLong' | 'innInvalid' | 'descriptionTooLong'
type ApiErrorKey = 'network' | 'rejected' | 'unknown'

/**
 * For signed-in users who are not sellers yet: the application form, or the status of the
 * latest application. When it is approved the tokens are refreshed to carry the seller role
 * and the panel opens.
 */
export function OnboardingPage() {
  const { t } = useTranslation()
  const me = useMe()
  const application = useSellerApplication()
  const [reapplying, setReapplying] = useState(false)
  usePromoteOnApproval(application.data ?? null, me.data?.role)

  let content
  if (me.data?.role === 'seller') return <Navigate to="/" replace />
  if (me.isPending || application.isPending) {
    content = (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label={t('common.loading')}>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  } else if (me.isError || application.isError) {
    content = (
      <QueryError
        error={me.error ?? application.error}
        onRetry={() => {
          void me.refetch()
          void application.refetch()
        }}
        retrying={me.isFetching || application.isFetching}
      />
    )
  } else if (me.data.role === 'admin') {
    content = <AdminNotice />
  } else {
    const current = application.data
    if (!current || (current.status === 'rejected' && reapplying)) {
      content = (
        <ApplyForm previous={current} onCancel={current ? () => setReapplying(false) : undefined} />
      )
    } else if (current.status === 'pending') {
      content = (
        <PendingStatus
          application={current}
          checking={application.isFetching}
          onCheck={() => void application.refetch()}
        />
      )
    } else if (current.status === 'rejected') {
      content = <RejectedStatus application={current} onReapply={() => setReapplying(true)} />
    } else {
      content = <ApprovedStatus />
    }
  }

  return (
    <AuthFrame>
      <title>{`${t('onboarding.title')} | ${t('common.panel')}`}</title>
      <div className="page-container flex justify-center py-8 sm:py-12">
        <Card padding="lg" className="w-full max-w-xl">
          {content}
        </Card>
      </div>
    </AuthFrame>
  )
}

/** Once approved, get tokens with the seller role and re-read the user (once per page visit). */
function usePromoteOnApproval(application: SellerApplication | null, role: string | undefined) {
  const { client } = useApi()
  const queryClient = useQueryClient()
  const done = useRef(false)
  useEffect(() => {
    if (application?.status !== 'approved' || role === 'seller' || done.current) return
    done.current = true
    void client
      .refresh()
      .catch(() => false)
      .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
  }, [application?.status, role, client, queryClient])
}

function Heading({
  icon,
  title,
  text,
  tone = 'primary',
}: {
  icon: ReactNode
  title: string
  text: string
  tone?: 'primary' | 'danger' | 'info'
}) {
  return (
    <div className="mb-6 flex flex-col gap-3">
      <span
        aria-hidden="true"
        className={cn(
          'grid size-11 place-items-center rounded-xl',
          tone === 'primary' && 'bg-primary-soft text-primary',
          tone === 'danger' && 'bg-danger-soft text-danger-ink',
          tone === 'info' && 'bg-info-soft text-info-ink',
        )}
      >
        {icon}
      </span>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text">{title}</h1>
      <p className="text-sm text-text-muted">{text}</p>
    </div>
  )
}

function ApplyForm({
  previous,
  onCancel,
}: {
  previous: SellerApplication | null
  onCancel?: () => void
}) {
  const { t } = useTranslation()
  const apply = useApplySeller()
  const application = useSellerApplication({ enabled: false })
  const { client } = useApi()
  const queryClient = useQueryClient()
  const [apiError, setApiError] = useState<ApiErrorKey | null>(null)
  const errorId = useId()
  const { register, handleSubmit, formState } = useForm<ApplyValues>({
    resolver: zodResolver(applySchema),
    defaultValues: {
      shop_name: previous?.shop_name ?? '',
      inn: previous?.inn ?? '',
      description: previous?.description ?? '',
    },
  })

  const onSubmit = handleSubmit((values) => {
    setApiError(null)
    apply.mutate(
      { shop_name: values.shop_name.trim(), inn: values.inn, description: values.description },
      {
        onError: (error) => {
          if (isApiError(error) && error.code === 'APPLICATION_PENDING') {
            void application.refetch()
          } else if (isApiError(error) && error.code === 'ALREADY_SELLER') {
            void client
              .refresh()
              .catch(() => false)
              .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
          } else if (isApiError(error) && error.code === CLIENT_ERROR.NETWORK) {
            setApiError('network')
          } else if (isApiError(error) && error.status === 400) {
            setApiError('rejected')
          } else {
            setApiError('unknown')
          }
        },
      },
    )
  })

  const fieldError = (name: keyof ApplyValues) => {
    const key = formState.errors[name]?.message as ApplyErrorKey | undefined
    return key ? t(`onboarding.errors.${key}`) : undefined
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <Heading
        icon={<Store size={22} strokeWidth={1.75} />}
        title={previous ? t('onboarding.reapplyTitle') : t('onboarding.title')}
        text={t('onboarding.subtitle')}
      />
      <Input
        {...register('shop_name')}
        label={t('onboarding.shopName')}
        hint={t('onboarding.shopNameHint')}
        error={fieldError('shop_name')}
        autoComplete="organization"
        maxLength={SHOP_NAME_MAX}
      />
      <Input
        {...register('inn')}
        label={t('onboarding.inn')}
        hint={t('onboarding.innHint')}
        error={fieldError('inn')}
        inputMode="numeric"
        maxLength={9}
        className="tabular"
      />
      <Textarea
        {...register('description')}
        label={t('onboarding.description')}
        hint={t('onboarding.descriptionHint')}
        error={fieldError('description')}
        maxLength={APPLICATION_DESCRIPTION_MAX}
      />
      {apiError && (
        <div
          id={errorId}
          role="alert"
          className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
        >
          <CircleAlert aria-hidden="true" size={18} strokeWidth={1.75} className="mt-px shrink-0" />
          <span>{t(`onboarding.errors.${apiError}`)}</span>
        </div>
      )}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
        )}
        <Button type="submit" size="lg" loading={apply.isPending}>
          {t('onboarding.submit')}
        </Button>
      </div>
    </form>
  )
}

function Summary({ application }: { application: SellerApplication }) {
  const { t } = useTranslation()
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 rounded-lg bg-surface-2 p-4 text-sm">
      <dt className="text-text-muted">{t('onboarding.shopName')}</dt>
      <dd className="font-semibold break-words text-text">{application.shop_name}</dd>
      <dt className="text-text-muted">{t('onboarding.inn')}</dt>
      <dd className="text-text tabular">{application.inn}</dd>
      <dt className="text-text-muted">{t('onboarding.sentAt')}</dt>
      <dd className="text-text tabular">{formatDateTime(application.created_at)}</dd>
    </dl>
  )
}

function PendingStatus({
  application,
  checking,
  onCheck,
}: {
  application: SellerApplication
  checking: boolean
  onCheck: () => void
}) {
  const { t } = useTranslation()
  const steps = [
    { key: 'sent', state: 'done' },
    { key: 'review', state: 'current' },
    { key: 'open', state: 'upcoming' },
  ] as const
  return (
    <div className="flex flex-col gap-6">
      <Heading
        tone="info"
        icon={<Clock size={22} strokeWidth={1.75} />}
        title={t('onboarding.pendingTitle')}
        text={t('onboarding.pendingText')}
      />
      <ol className="flex flex-col gap-0" aria-label={t('onboarding.stepsLabel')}>
        {steps.map((step, index) => (
          <li key={step.key} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold tabular',
                  step.state === 'done' && 'bg-primary text-primary-fg',
                  step.state === 'current' && 'bg-info-soft text-info-ink ring-2 ring-info',
                  step.state === 'upcoming' && 'bg-surface-2 text-text-muted',
                )}
                aria-hidden="true"
              >
                {step.state === 'done' ? <Check size={14} strokeWidth={3} /> : index + 1}
              </span>
              {index < steps.length - 1 && (
                <span aria-hidden="true" className="my-1 w-px flex-1 bg-border" />
              )}
            </div>
            <div className="pb-5">
              <p
                className={cn(
                  'text-sm font-semibold',
                  step.state === 'upcoming' ? 'text-text-muted' : 'text-text',
                )}
                aria-current={step.state === 'current' ? 'step' : undefined}
              >
                {t(`onboarding.steps.${step.key}`)}
              </p>
              <p className="text-sm text-text-muted">{t(`onboarding.steps.${step.key}Hint`)}</p>
            </div>
          </li>
        ))}
      </ol>
      <Summary application={application} />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          onClick={onCheck}
          loading={checking}
          leadingIcon={<RotateCw aria-hidden="true" size={18} strokeWidth={1.75} />}
        >
          {t('onboarding.check')}
        </Button>
        <p className="text-sm text-text-muted">{t('onboarding.autoCheck')}</p>
      </div>
    </div>
  )
}

function RejectedStatus({
  application,
  onReapply,
}: {
  application: SellerApplication
  onReapply: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-6">
      <Heading
        tone="danger"
        icon={<XCircle size={22} strokeWidth={1.75} />}
        title={t('onboarding.rejectedTitle')}
        text={t('onboarding.rejectedText')}
      />
      <Summary application={application} />
      {application.reviewed_at && (
        <p className="text-sm text-text-muted tabular">
          {t('onboarding.reviewedAt', { date: formatDateTime(application.reviewed_at) })}
        </p>
      )}
      <Button size="lg" onClick={onReapply} className="self-start">
        {t('onboarding.reapply')}
      </Button>
    </div>
  )
}

function ApprovedStatus() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center" role="status">
      <Spinner className="size-6 text-primary" />
      <h1 className="font-heading text-2xl font-extrabold text-text">
        {t('onboarding.approvedTitle')}
      </h1>
      <p className="text-sm text-text-muted">{t('onboarding.approvedText')}</p>
    </div>
  )
}

function AdminNotice() {
  const { t } = useTranslation()
  return (
    <Heading
      tone="info"
      icon={<Store size={22} strokeWidth={1.75} />}
      title={t('onboarding.adminTitle')}
      text={t('onboarding.adminText')}
    />
  )
}
