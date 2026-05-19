import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { getSession, login, logout, type LoginInput } from "@/lib/api/auth"
import { isApiError } from "@/lib/api/errors"

export function useSessionQuery() {
  return useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      try {
        return await getSession()
      } catch (error) {
        if (isApiError(error) && error.kind === "unauthorized") {
          return { authenticated: false as const }
        }
        throw error
      }
    },
    retry: false,
  })
}

export function useLoginMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: LoginInput) => login(input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["session"] })
    },
  })
}

export function useLogoutMutation(onClearPreferences: () => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: logout,
    onSettled: async () => {
      onClearPreferences()
      queryClient.clear()
    },
  })
}
