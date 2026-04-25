/**
 * Generic HTTP client infrastructure for the REST API.
 *
 * Houses the shared `request()` fetcher, query-string builder, and
 * `ApiError` class. Domain modules (`spawns.ts`, `chats.ts`, `work.ts`)
 * import these internals — consumers should not need to use them directly
 * except for `ApiError` (re-exported from the barrel).
 */

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

// ---------------------------------------------------------------------------
// Query builder
// ---------------------------------------------------------------------------

export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  }
  return parts.length === 0 ? '' : `?${parts.join('&')}`
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

export async function request(path: string, init?: RequestInit): Promise<void>
export async function request<T>(path: string, init?: RequestInit): Promise<T>
export async function request<T = void>(
  path: string,
  init?: RequestInit,
): Promise<T | void> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string; message?: string }
      detail = body.detail ?? body.message ?? detail
    } catch {
      // non-JSON body — keep statusText
    }
    throw new ApiError(response.status, `${response.status} ${detail}`)
  }

  // 204 / empty body
  if (response.status === 204) return undefined
  const text = await response.text()
  if (!text) return undefined
  return JSON.parse(text) as T
}
