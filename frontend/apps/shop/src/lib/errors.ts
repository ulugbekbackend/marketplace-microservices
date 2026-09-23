import { isApiError } from '@bozorcha/api-client'

export const isNotFound = (error: unknown) => isApiError(error) && error.status === 404
