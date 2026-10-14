import type { QualityDecision, VideoDecision } from '../types'

export interface SubmitOptions {
  fetchFn?: typeof fetch
}

/** Use a deployed API URL when configured; keep relative /api paths for local Vite proxying. */
export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_VISIONFIT_API_URL?.trim().replace(/\/+$/, '')
  return base ? `${base}${path}` : path
}

/**
 * Build an actionable error for a fetch that rejected (e.g. the browser's generic
 * "Failed to fetch"). This is a network-level failure — no HTTP response was
 * received — so the cause is an unreachable service, a cross-origin block or an
 * interrupted upload, rather than a decision the service returned.
 */
function networkError(path: string): Error {
  return new Error(
    `Could not reach the analysis service at ${apiUrl(path)}. ` +
      'Check that the VisionFit service is running and reachable, that the API URL is correct, ' +
      'and that this origin is allowed by the service.',
  )
}

/** POST one image (front or side) to the quality service and return its decision. */
export async function submitQualityCheck(
  image: File,
  view: 'front' | 'side',
  options: SubmitOptions = {},
): Promise<QualityDecision> {
  const fetchFn = options.fetchFn ?? fetch
  const form = new FormData()
  form.append('view', view)
  form.append('file', image)

  let response: Response
  try {
    response = await fetchFn(apiUrl('/api/quality'), { method: 'POST', body: form })
  } catch {
    throw networkError('/api/quality')
  }
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Quality check failed (${response.status}): ${detail}`)
  }
  return (await response.json()) as QualityDecision
}

export async function submitCaptureCheck(image: File, view: 'front' | 'side', consent: boolean): Promise<QualityDecision> {
  const form = new FormData()
  form.append('view', view)
  form.append('consent', String(consent))
  form.append('file', image)

  let response: Response
  try {
    response = await fetch(apiUrl('/api/capture'), { method: 'POST', body: form })
  } catch {
    throw networkError('/api/capture')
  }
  if (!response.ok) throw new Error(`Capture check failed (${response.status}): ${await response.text()}`)
  return await response.json()
}

/** POST a slow-turn video to the service and return its review decision. */
export async function submitTurnVideoCheck(file: File, consent: boolean): Promise<VideoDecision> {
  const form = new FormData()
  form.append('consent', String(consent))
  form.append('file', file)

  let response: Response
  try {
    response = await fetch(apiUrl('/api/turn-video'), { method: 'POST', body: form })
  } catch {
    throw networkError('/api/turn-video')
  }
  if (!response.ok) throw new Error(`Video check failed (${response.status}): ${await response.text()}`)
  return (await response.json()) as VideoDecision
}
