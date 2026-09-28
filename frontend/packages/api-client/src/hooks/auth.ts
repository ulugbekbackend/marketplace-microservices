import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ApiError } from '../errors'
import type { OtpVerifyResponse, User, UserUpdateRequest } from '../types'
import { useApi, useSession } from './context'
import { queryKeys } from './keys'

/** Current user; only fetched while a session exists. */
export function useMe() {
  const { auth } = useApi()
  const { isAuthenticated } = useSession()
  return useQuery<User, ApiError>({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => auth.me(signal),
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
  })
}

export function useSendOtp() {
  const { auth } = useApi()
  return useMutation<void, ApiError, { phone: string }>({
    mutationFn: ({ phone }) => auth.sendOtp(phone),
  })
}

export function useVerifyOtp() {
  const { auth } = useApi()
  const queryClient = useQueryClient()
  return useMutation<OtpVerifyResponse, ApiError, { phone: string; code: string }>({
    mutationFn: ({ phone, code }) => auth.verifyOtp(phone, code),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.me, data.user),
  })
}

export function useUpdateMe() {
  const { auth } = useApi()
  const queryClient = useQueryClient()
  return useMutation<User, ApiError, UserUpdateRequest>({
    mutationFn: (body) => auth.updateMe(body),
    onSuccess: (user) => queryClient.setQueryData(queryKeys.me, user),
  })
}

export function useLogout() {
  const { auth } = useApi()
  const queryClient = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () => auth.logout(),
    // Local tokens are cleared even if the server call fails. The customer's cart, favorites and orders
    // must not stay on screen: the cart is refetched as the guest's.
    onSettled: () => {
      queryClient.removeQueries({ queryKey: queryKeys.me })
      queryClient.removeQueries({ queryKey: queryKeys.favorites })
      queryClient.removeQueries({ queryKey: queryKeys.orders })
      queryClient.removeQueries({ queryKey: queryKeys.sellerApplication })
      queryClient.removeQueries({ queryKey: queryKeys.sellerProducts })
      void queryClient.resetQueries({ queryKey: queryKeys.cart })
    },
  })
}
