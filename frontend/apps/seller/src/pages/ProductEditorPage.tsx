import {
  invalidateSellerLists,
  isApiError,
  queryKeys,
  useApi,
  useAttributes,
  useCategories,
  useSellerProduct,
  type Attribute,
  type Category,
  type SellerProductDetail,
} from '@bozorcha/api-client'
import { Button, Card, EmptyState, Input, Select, Skeleton, Textarea, useToast } from '@bozorcha/ui'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CircleAlert, PackageX } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ProductImages } from '../components/ProductImages'
import { ProductStatusBadge } from '../components/ProductStatusBadge'
import { QueryError } from '../components/QueryError'
import { VariantMatrix, type MatrixState } from '../components/VariantMatrix'
import { flattenCategories, indentedLabel } from '../lib/categories'
import { formatDateTime } from '../lib/dates'
import {
  DESCRIPTION_MAX,
  hasMatrixErrors,
  productSchema,
  TITLE_MAX,
  validateMatrix,
  type FieldError,
  type ProductValues,
  type RowErrors,
} from '../lib/productForm'
import { productSaveError, saveProduct } from '../lib/saveProduct'
import { initialMatrix, refreshAutoSkus, skuBase, syncRows } from '../lib/variantMatrix'

/** `/products/new` creates, `/products/:id` edits; one form either way. */
export function ProductEditorPage() {
  const { t } = useTranslation()
  const { productId = 'new' } = useParams()
  const location = useLocation()
  const isNew = productId === 'new'
  // After the first save the URL gets the new id, but the same form stays mounted.
  const justCreated = (location.state as { created?: boolean } | null)?.created === true
  const product = useSellerProduct(isNew ? undefined : productId)
  const attributes = useAttributes()
  const categories = useCategories()

  const failed = [!isNew && product.error, attributes.error, categories.error].find(Boolean)
  if (!isNew && isApiError(product.error) && product.error.status === 404) {
    return (
      <Page>
        <EmptyState
          icon={<PackageX size={22} strokeWidth={1.75} />}
          title={t('productForm.notFound')}
          description={t('productForm.notFoundHint')}
          action={<BackLink />}
        />
      </Page>
    )
  }
  if (failed) {
    return (
      <Page>
        <QueryError
          error={failed}
          onRetry={() => {
            if (!isNew) void product.refetch()
            void attributes.refetch()
            void categories.refetch()
          }}
        />
      </Page>
    )
  }
  if ((!isNew && !product.data) || !attributes.data || !categories.data) {
    return (
      <Page>
        <div aria-busy="true" aria-label={t('common.loading')} className="flex flex-col gap-4">
          <Skeleton className="h-8 w-64" />
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="flex flex-col gap-4">
              <Skeleton className="h-64 w-full rounded-xl" />
              <Skeleton className="h-80 w-full rounded-xl" />
            </div>
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        </div>
      </Page>
    )
  }

  return (
    <ProductForm
      key={justCreated ? 'new' : productId}
      productId={isNew ? null : productId}
      initial={isNew ? null : product.data!}
      live={isNew ? null : (product.data ?? null)}
      attributes={attributes.data}
      categories={categories.data}
    />
  )
}

function Page({ children }: { children: ReactNode }) {
  return <div className="page-container flex flex-col gap-5 py-6 sm:py-8">{children}</div>
}

function BackLink() {
  const { t } = useTranslation()
  return (
    <Link
      to="/products"
      className="inline-flex h-10 items-center gap-1.5 self-start rounded-lg px-2 text-sm font-semibold text-text-muted hover:bg-surface-2 hover:text-text focus-ring"
    >
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      {t('productForm.back')}
    </Link>
  )
}

type ProductFormProps = {
  productId: string | null
  /** Server state when the form was opened (null for a new product). */
  initial: SellerProductDetail | null
  /** Latest server state, polled while images are processed. */
  live: SellerProductDetail | null
  attributes: Attribute[]
  categories: Category[]
}

function ProductForm({ productId, initial, live, attributes, categories }: ProductFormProps) {
  const { t } = useTranslation()
  const { seller } = useApi()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const formErrorId = useId()
  const categoryOptions = useMemo(() => flattenCategories(categories), [categories])

  const { register, handleSubmit, formState, control } = useForm<ProductValues>({
    resolver: zodResolver(productSchema),
    defaultValues: {
      title: initial?.title ?? '',
      category_id: initial?.category.id ?? '',
      description: initial?.description ?? '',
      status: initial?.status ?? 'draft',
    },
  })
  const title = useWatch({ control, name: 'title' })
  const status = useWatch({ control, name: 'status' })
  const base = skuBase(title)

  const [matrix, setMatrix] = useState<MatrixState>(() =>
    initial
      ? initialMatrix(initial.variants, attributes, skuBase(initial.title))
      : { selection: [], rows: syncRows([], [], attributes, skuBase('')) },
  )
  const [baseline, setBaseline] = useState<SellerProductDetail | null>(initial)
  const [rowErrors, setRowErrors] = useState<Record<string, RowErrors>>({})
  const [matrixError, setMatrixError] = useState<FieldError | null>(null)
  const [saveError, setSaveError] = useState<FieldError | null>(null)
  const savedId = productId ?? baseline?.id ?? null

  const save = useMutation({
    mutationFn: (values: ProductValues) =>
      saveProduct(seller, { productId: savedId, values, baseline, rows: matrix.rows }),
    onSuccess: (result) => {
      setBaseline(result.product)
      setMatrix((current) => ({ ...current, rows: result.rows }))
      setRowErrors(result.failures)
      queryClient.setQueryData(queryKeys.sellerProduct(result.product.id), result.product)
      void invalidateSellerLists(queryClient)
      const failedCount = Object.keys(result.failures).length
      // Stayed a draft although "Sotuvda" was chosen: say so where the save errors show.
      setSaveError(result.activation)
      if (result.activation) {
        toast({ tone: 'danger', title: t('productForm.partiallySaved') })
      } else if (failedCount === 0) {
        toast({ tone: 'success', title: t('productForm.saved') })
      } else {
        toast({
          tone: 'danger',
          title: t('productForm.partiallySaved'),
          description: t('productForm.variantsFailed', { count: failedCount }),
        })
      }
      if (!savedId) {
        navigate(`/products/${result.product.id}`, { replace: true, state: { created: true } })
      }
    },
    onError: (error) => setSaveError(productSaveError(error)),
  })

  const onSubmit = handleSubmit((values) => {
    setSaveError(null)
    const validation = validateMatrix(matrix.rows, values.status)
    setRowErrors(validation.rows)
    setMatrixError(validation.form)
    if (hasMatrixErrors(validation)) {
      // Move focus to the first invalid variant field so keyboard users land on it.
      requestAnimationFrame(() =>
        document.querySelector<HTMLElement>('[data-row] [aria-invalid="true"]')?.focus(),
      )
      return
    }
    save.mutate(values)
  })

  const fieldError = (key: string | undefined) =>
    key
      ? t(`productForm.errors.${key}` as 'productForm.errors.titleRequired', { max: TITLE_MAX })
      : undefined

  const statusOptions = (
    savedId ? (['draft', 'active', 'archived'] as const) : (['draft', 'active'] as const)
  ).map((value) => ({ value, label: t(`productStatus.${value}`) }))
  const images = live?.images ?? baseline?.images ?? []
  const heading = savedId
    ? baseline?.title || t('productForm.editTitle')
    : t('productForm.newTitle')

  return (
    <Page>
      <title>{`${heading} | ${t('common.panel')}`}</title>
      <BackLink />
      <form onSubmit={onSubmit} noValidate aria-describedby={saveError ? formErrorId : undefined}>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h1 className="min-w-0 font-heading text-2xl font-extrabold tracking-tight break-words text-text sm:text-3xl">
              {heading}
            </h1>
            {baseline && <ProductStatusBadge status={baseline.status} />}
          </div>
          <Button
            type="submit"
            size="lg"
            loading={save.isPending}
            className="hidden sm:inline-flex"
          >
            {t('common.save')}
          </Button>
        </div>

        {saveError && (
          <div
            id={formErrorId}
            role="alert"
            className="mb-5 flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
          >
            <CircleAlert
              aria-hidden="true"
              size={18}
              strokeWidth={1.75}
              className="mt-px shrink-0"
            />
            {t(
              `productForm.errors.${saveError.key}` as 'productForm.errors.unknown',
              saveError.params,
            )}
          </div>
        )}

        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex min-w-0 flex-col gap-5">
            <Section title={t('productForm.basics')}>
              <Input
                {...register('title', {
                  onChange: (event: { target: { value: string } }) =>
                    setMatrix((current) => ({
                      ...current,
                      rows: refreshAutoSkus(current.rows, skuBase(event.target.value)),
                    })),
                })}
                label={t('productForm.title')}
                error={fieldError(formState.errors.title?.message)}
                maxLength={TITLE_MAX}
                placeholder={t('productForm.titlePlaceholder')}
              />
              <Select
                {...register('category_id')}
                label={t('productForm.category')}
                placeholder={t('productForm.categoryPlaceholder')}
                error={fieldError(formState.errors.category_id?.message)}
              >
                {categoryOptions.map((option) => (
                  <option key={option.id} value={option.id} title={option.path}>
                    {indentedLabel(option)}
                  </option>
                ))}
              </Select>
              <Textarea
                {...register('description')}
                label={t('productForm.description')}
                hint={t('productForm.descriptionHint', { max: DESCRIPTION_MAX })}
                error={
                  formState.errors.description
                    ? t('productForm.errors.descriptionTooLong', { max: DESCRIPTION_MAX })
                    : undefined
                }
                rows={5}
              />
            </Section>

            <Section title={t('productForm.variants')} description={t('productForm.variantsHint')}>
              <VariantMatrix
                attributes={attributes}
                state={matrix}
                onChange={(next) => {
                  setMatrix(next)
                  setMatrixError(null)
                }}
                skuBase={base}
                errors={rowErrors}
                formError={matrixError}
              />
            </Section>

            <Section title={t('productForm.images')} description={t('productForm.imagesHint')}>
              <ProductImages productId={savedId} images={images} />
            </Section>
          </div>

          <aside className="flex flex-col gap-5 lg:sticky lg:top-24">
            <Section title={t('productForm.publishing')}>
              <Select
                {...register('status')}
                label={t('productForm.status')}
                options={statusOptions}
                hint={t(`productForm.statusHint.${status}`)}
              />
              <Button type="submit" size="lg" fullWidth loading={save.isPending}>
                {t('common.save')}
              </Button>
              {baseline && (
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-text-muted">{t('productForm.created')}</dt>
                  <dd className="text-right text-text tabular">
                    {formatDateTime(baseline.created_at)}
                  </dd>
                  <dt className="text-text-muted">{t('productForm.updated')}</dt>
                  <dd className="text-right text-text tabular">
                    {formatDateTime(baseline.updated_at)}
                  </dd>
                </dl>
              )}
            </Section>
          </aside>
        </div>
      </form>
    </Page>
  )
}

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  const id = useId()
  return (
    <Card padding="lg" className="flex flex-col gap-4" role="group" aria-labelledby={id}>
      <div>
        <h2 id={id} className="font-heading text-lg font-bold text-text">
          {title}
        </h2>
        {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
      </div>
      {children}
    </Card>
  )
}
