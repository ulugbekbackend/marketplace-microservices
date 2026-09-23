import { useSendOtp, useSession, useVerifyOtp } from '@bozorcha/api-client'
import { Button, Card, Input, OtpInput, useToast } from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { CircleAlert, MessageSquareText, Smartphone } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'
import { loginErrorKey, retryAfterSeconds, type LoginErrorKey } from '../lib/authErrors'
import { formatE164, formatNational, nationalDigits, toE164, UZ_COUNTRY_CODE } from '../lib/phone'
import { safeNext } from '../lib/redirect'
import { formatMmSs, useCountdown } from '../lib/useCountdown'

const RESEND_SECONDS = 60
const CODE_LENGTH = 6

const phoneSchema = z.object({
  phone: z
    .string()
    .min(1, 'phoneRequired')
    .refine((value) => nationalDigits(value).length === 9, 'phoneInvalid'),
})
type PhoneForm = z.infer<typeof phoneSchema>

const codeSchema = z.object({
  code: z.string().regex(new RegExp(`^\\d{${CODE_LENGTH}}$`), 'codeRequired'),
})
type CodeForm = z.infer<typeof codeSchema>

export function LoginPage() {
  const { t } = useTranslation()
  const { isAuthenticated } = useSession()
  const [searchParams] = useSearchParams()
  const next = safeNext(searchParams.get('next'))
  const [phone, setPhone] = useState<string | null>(null)
  const [resendAt, setResendAt] = useState<number | null>(null)
  // Only users who arrive already signed in are bounced. A login that completes here navigates
  // from the verify handler, after its toast; redirecting on the session change instead would
  // unmount the form before that handler runs.
  const [signedInOnArrival] = useState(isAuthenticated)

  if (signedInOnArrival) return <Navigate to={next} replace />

  return (
    <div className="page-container flex justify-center py-8 sm:py-14">
      <title>{`${t('login.title')} | ${t('common.brand')}`}</title>
      <Card padding="lg" className="w-full max-w-md">
        {phone === null ? (
          <PhoneStep
            onSent={(sentTo) => {
              setPhone(sentTo)
              setResendAt(Date.now() + RESEND_SECONDS * 1000)
            }}
          />
        ) : (
          <CodeStep
            phone={phone}
            resendAt={resendAt}
            onResendAt={setResendAt}
            onChangePhone={() => setPhone(null)}
            next={next}
          />
        )}
      </Card>
    </div>
  )
}

function StepHeader({
  icon,
  title,
  subtitle,
}: {
  icon: ReactNode
  title: string
  subtitle: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-col gap-3">
      <span
        className="grid size-11 place-items-center rounded-xl bg-primary-soft text-primary"
        aria-hidden="true"
      >
        {icon}
      </span>
      <h1 className="font-heading text-2xl font-extrabold tracking-tight text-text">{title}</h1>
      <p className="text-sm text-text-muted">{subtitle}</p>
    </div>
  )
}

function FormError({ id, messageKey }: { id: string; messageKey: LoginErrorKey | null }) {
  const { t } = useTranslation()
  if (!messageKey) return null
  return (
    <div
      id={id}
      role="alert"
      className="flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
    >
      <CircleAlert aria-hidden="true" size={18} strokeWidth={1.75} className="mt-px shrink-0" />
      <span>{t(`login.errors.${messageKey}`)}</span>
    </div>
  )
}

function PhoneStep({ onSent }: { onSent: (phone: string) => void }) {
  const { t } = useTranslation()
  const sendOtp = useSendOtp()
  const [apiError, setApiError] = useState<LoginErrorKey | null>(null)
  const errorId = useId()
  const { control, handleSubmit, formState } = useForm<PhoneForm>({
    resolver: zodResolver(phoneSchema),
    defaultValues: { phone: '' },
  })

  const onSubmit = handleSubmit(({ phone }) => {
    setApiError(null)
    const e164 = toE164(phone)
    sendOtp.mutate(
      { phone: e164 },
      {
        onSuccess: () => onSent(e164),
        onError: (error) => setApiError(loginErrorKey(error)),
      },
    )
  })

  const fieldError = formState.errors.phone?.message
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <StepHeader
        icon={<Smartphone size={22} strokeWidth={1.75} />}
        title={t('login.title')}
        subtitle={t('login.phoneSubtitle')}
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
            onChange={(event) => {
              setApiError(null)
              field.onChange(formatNational(event.target.value))
            }}
            label={t('login.phoneLabel')}
            hint={t('login.phoneHint')}
            error={
              fieldError
                ? t(`login.errors.${fieldError as 'phoneRequired' | 'phoneInvalid'}`)
                : apiError === 'INVALID_PHONE'
                  ? t('login.errors.INVALID_PHONE')
                  : undefined
            }
            prefix={
              <span className="text-base font-medium text-text tabular">{UZ_COUNTRY_CODE}</span>
            }
            className="pl-16 tabular"
            type="tel"
            inputMode="tel"
            autoComplete="tel-national"
            placeholder="90 123 45 67"
            // eslint-disable-next-line jsx-a11y/no-autofocus -- the phone number is the page's only task
            autoFocus
          />
        )}
      />
      {apiError !== 'INVALID_PHONE' && <FormError id={errorId} messageKey={apiError} />}
      <Button type="submit" size="lg" fullWidth loading={sendOtp.isPending}>
        {t('login.sendCode')}
      </Button>
      <p className="text-center text-xs text-text-muted">{t('login.terms')}</p>
    </form>
  )
}

function CodeStep({
  phone,
  resendAt,
  onResendAt,
  onChangePhone,
  next,
}: {
  phone: string
  resendAt: number | null
  onResendAt: (at: number | null) => void
  onChangePhone: () => void
  next: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { toast } = useToast()
  const verify = useVerifyOtp()
  const resend = useSendOtp()
  const secondsLeft = useCountdown(resendAt)
  const [apiError, setApiError] = useState<LoginErrorKey | null>(null)
  const errorId = useId()
  const { control, handleSubmit, formState, setValue } = useForm<CodeForm>({
    resolver: zodResolver(codeSchema),
    defaultValues: { code: '' },
  })
  const blocked = apiError === 'OTP_BLOCKED'

  const onSubmit = handleSubmit(({ code }) => {
    if (verify.isPending || blocked) return
    setApiError(null)
    verify.mutate(
      { phone, code },
      {
        onSuccess: () => {
          toast({ title: t('login.welcome'), tone: 'success' })
          navigate(next, { replace: true })
        },
        onError: (error) => {
          const key = loginErrorKey(error)
          setApiError(key)
          // An expired code cannot be fixed by retyping: allow requesting a new one now.
          if (key === 'OTP_EXPIRED') onResendAt(null)
          if (key === 'OTP_INVALID' || key === 'OTP_EXPIRED') setValue('code', '')
        },
      },
    )
  })

  const onResend = () => {
    setApiError(null)
    resend.mutate(
      { phone },
      {
        onSuccess: () => {
          setValue('code', '')
          onResendAt(Date.now() + RESEND_SECONDS * 1000)
          toast({ title: t('login.resent'), tone: 'success' })
        },
        onError: (error) => {
          setApiError(loginErrorKey(error))
          const wait = retryAfterSeconds(error)
          if (wait) onResendAt(Date.now() + wait * 1000)
        },
      },
    )
  }

  const fieldError = formState.errors.code?.message ? 'codeRequired' : null
  const shownError: LoginErrorKey | 'codeRequired' | null = apiError ?? fieldError

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
      <StepHeader
        icon={<MessageSquareText size={22} strokeWidth={1.75} />}
        title={t('login.codeTitle')}
        subtitle={
          <>
            {t('login.codeSubtitle', { phone: formatE164(phone) })}{' '}
            <button
              type="button"
              onClick={onChangePhone}
              className="rounded-sm font-semibold text-primary hover:underline focus-ring"
            >
              {t('login.changePhone')}
            </button>
          </>
        }
      />
      <Controller
        control={control}
        name="code"
        render={({ field }) => (
          <OtpInput
            value={field.value}
            onChange={(value) => {
              if (apiError && apiError !== 'OTP_BLOCKED') setApiError(null)
              field.onChange(value)
            }}
            onComplete={() => void onSubmit()}
            length={CODE_LENGTH}
            label={t('login.codeLabel')}
            cellLabel={(index, count) => t('login.codeCell', { index: index + 1, count })}
            invalid={shownError !== null}
            disabled={blocked || verify.isPending}
            describedBy={shownError ? errorId : undefined}
            // eslint-disable-next-line jsx-a11y/no-autofocus -- entering the code is the only task of this step
            autoFocus
            className="mx-auto"
          />
        )}
      />
      {shownError === 'codeRequired' ? (
        <p id={errorId} role="alert" className="text-sm text-danger-ink">
          {t('login.errors.codeRequired')}
        </p>
      ) : (
        <FormError id={errorId} messageKey={shownError} />
      )}
      <Button type="submit" size="lg" fullWidth loading={verify.isPending} disabled={blocked}>
        {t('login.verify')}
      </Button>
      <div className="flex justify-center">
        {secondsLeft > 0 ? (
          <p className="text-sm text-text-muted tabular" aria-live="off">
            {t('login.resendIn', { time: formatMmSs(secondsLeft) })}
          </p>
        ) : (
          <Button variant="ghost" onClick={onResend} loading={resend.isPending} disabled={blocked}>
            {t('login.resend')}
          </Button>
        )}
      </div>
    </form>
  )
}
