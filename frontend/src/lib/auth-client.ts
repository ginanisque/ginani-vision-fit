import { createAuthClient } from '@neondatabase/auth'
import { BetterAuthReactAdapter } from '@neondatabase/auth/react/adapters'

const authUrl = import.meta.env.VITE_NEON_AUTH_URL || 'http://localhost.invalid/auth'

export const authClient = createAuthClient(authUrl, {
  adapter: BetterAuthReactAdapter(),
})

export async function bearerToken(): Promise<string> {
  const { data, error } = await authClient.token()
  if (error || !data?.token) throw new Error('Your session has expired. Please sign in again.')
  return data.token
}
