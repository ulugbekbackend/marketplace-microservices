import {
  CLIENT_ERROR,
  isApiError,
  queryKeys,
  useApi,
  useApplySeller,
  useMe,
  useSellerApplication,
  type SellerApplication,
  type SellerBusinessType,
} from '@bozorcha/api-client'
import { Button, Card, cn, Input, Skeleton, Spinner, Textarea } from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Building2, Check, CircleAlert, Clock, RotateCw, Store, User, XCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useForm, useWatch, type UseFormRegisterReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router'
import { z } from 'zod'
import { AuthFrame } from '../components/layout/AuthFrame'
import { QueryError } from '../components/QueryError'
import { formatDateTime } from '../lib/dates'

const SHOP_NAME_MAX = 120
const APPLICATION_DESCRIPTION_MAX = 2000

const BUSINESS_TYPES = [
  'llc',
  'sole_proprietor',
  'self_employed',
] as const satisfies readonly SellerBusinessType[]
const STIR = /^\d{9}$/
const STIR_OR_PINFL = /^(\d{9}|\d{14})$/

/** Until a type is picked the form asks for a STIR, the one id every type may use. */
const isCompany = (type: SellerBusinessType | null | undefined) => !type || type === 'llc'

// A company applies with its STIR; a sole proprietor or a self-employed person may also use
// the 14 digit JShShIR (PINFL).
const applySchema = z
  .object({
    shop_name: z.string().trim().min(2, 'shopNameRequired').max(SHOP_NAME_MAX, 'shopNameTooLong'),
    business_type: z.enum(BUSINESS_TYPES).nullish(), // an untouched radio group is null
    tax_id: z.string(),
    description: z.string().max(APPLICATION_DESCRIPTION_MAX, 'descriptionTooLong'),
  })
  .superRefine(
    (values, ctx) => {
      if (!values.business_type) {
        ctx.addIssue({ code: 'custom', path: ['business_type'], message: 'businessTypeRequired' })
      }
      const company = isCompany(values.business_type)
      if (!(company ? STIR : STIR_OR_PINFL).test(values.tax_id)) {
        const message = company ? 'stirInvalid' : 'taxIdInvalid'
        ctx.addIssue({ code: 'custom', path: ['tax_id'], message })
      }
    },
    // Run even when other fields fail, so that every error shows at once. The form always
    // holds strings, so the values are safe to read.
    { when: () => true },
  )
type ApplyValues = z.infer<typeof applySchema>
type ApplyErrorKey =
  | 'shopNameRequired'
  | 'shopNameTooLong'
  | 'businessTypeRequired'
  | 'stirInvalid'
  | 'taxIdInvalid'
  | 'descriptionTooLong'
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
  const { control, register, handleSubmit, formState } = useForm<ApplyValues>({
    resolver: zodResolver(applySchema),
    defaultValues: {
      shop_name: previous?.shop_name ?? '',
      business_type: previous?.business_type,
      tax_id: previous?.tax_id ?? '',
      description: previous?.description ?? '',
    },
  })
  const businessType = useWatch({ control, name: 'business_type' })
  const company = isCompany(businessType)

  const onSubmit = handleSubmit(({ business_type, ...values }) => {
    if (!business_type) return // the schema has already reported it
    setApiError(null)
    apply.mutate(
      {
        shop_name: values.shop_name.trim(),
        business_type,
        tax_id: values.tax_id,
        description: values.description,
      },
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
      <BusinessTypeField
        register={register('business_type')}
        selected={businessType}
        error={fieldError('business_type')}
      />
      <Input
        {...register('tax_id')}
        label={t(company ? 'onboarding.stir' : 'onboarding.taxId')}
        hint={t(company ? 'onboarding.stirHint' : 'onboarding.taxIdHint')}
        error={fieldError('tax_id')}
        inputMode="numeric"
        maxLength={company ? 9 : 14}
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

function BusinessTypeField({
  register,
  selected,
  error,
}: {
  register: UseFormRegisterReturn<'business_type'>
  selected: SellerBusinessType | null | undefined
  error: string | undefined
}) {
  const { t } = useTranslation()
  const errorId = useId()
  return (
    <fieldset
      className="flex flex-col gap-2"
      aria-invalid={error ? true : undefined}
      aria-describedby={error ? errorId : undefined}
    >
      <legend className="mb-1.5 text-sm font-medium text-text">
        {t('onboarding.businessType')}
      </legend>
      <div className="flex flex-col gap-2">
        {BUSINESS_TYPES.map((type) => {
          const Icon = type === 'llc' ? Building2 : User
          return (
            <label
              key={type}
              className={cn(
                'flex min-h-14 cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-150 ease-out has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary',
                selected === type
                  ? 'border-primary bg-primary-soft text-text'
                  : 'border-border bg-surface text-text hover:bg-surface-2',
              )}
            >
              <input
                {...register}
                type="radio"
                value={type}
                className="mt-0.5 size-4 shrink-0 accent-primary"
              />
              <Icon
                aria-hidden="true"
                size={18}
                strokeWidth={1.75}
                className="mt-px shrink-0 text-text-muted"
              />
              <span className="flex min-w-0 flex-col text-sm font-semibold">
                {t(`onboarding.businessTypes.${type}`)}
                <span className="text-xs font-normal text-text-muted">
                  {t(`onboarding.businessTypeHints.${type}`)}
                </span>
              </span>
            </label>
          )
        })}
      </div>
      {error && (
        <p id={errorId} className="text-sm text-danger-ink">
          {error}
        </p>
      )}
    </fieldset>
  )
}

function Summary({ application }: { application: SellerApplication }) {
  const { t } = useTranslation()
  const company = application.business_type === 'llc'
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 rounded-lg bg-surface-2 p-4 text-sm">
      <dt className="text-text-muted">{t('onboarding.shopName')}</dt>
      <dd className="font-semibold break-words text-text">{application.shop_name}</dd>
      <dt className="text-text-muted">{t('onboarding.businessType')}</dt>
      <dd className="text-text">{t(`onboarding.businessTypes.${application.business_type}`)}</dd>
      <dt className="text-text-muted">{t(company ? 'onboarding.stir' : 'onboarding.taxId')}</dt>
      <dd className="text-text tabular">{application.tax_id}</dd>
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
