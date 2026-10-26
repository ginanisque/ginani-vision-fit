import type { AnalysisDecisionDto, AuthSession, CalibrationKind, CaptureSessionDetailDto, CaptureSessionSummaryDto, CircumferenceEstimate, CustomerDto, MeasurementDefinitionDto, MeasurementPathDto, MeasurementReadinessDto, MeasurementTableDto, QualityDecision, VideoDecision } from '../types'
import { authClient, bearerToken } from './auth-client'

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
  image: File, view: 'front' | 'side', consent: boolean,
  options: SubmitOptions = {},
): Promise<QualityDecision> {
  const fetchFn = options.fetchFn ?? fetch
  const form = new FormData()
  form.append('view', view)
  form.append('consent', String(consent))
  form.append('file', image)

  let response: Response
  try {
    response = await fetchFn(apiUrl('/api/quality'), {
      method: 'POST', body: form, headers: await authorization(),
    })
  } catch {
    throw networkError('/api/quality')
  }
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Quality check failed (${response.status}): ${detail}`)
  }
  return (await response.json()) as QualityDecision
}

async function authorization(): Promise<Record<string, string>> {
  return { Authorization: `Bearer ${await bearerToken()}` }
}

async function authenticatedFetch(path: string, init: RequestInit): Promise<Response> {
  const request = async (forceRefresh = false) => fetch(apiUrl(path), {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${await bearerToken(forceRefresh)}` },
  })
  let response = await request()
  if (response.status === 401) response = await request(true)
  return response
}

export async function submitCaptureCheck(
  image: File, view: 'front' | 'side' | 'back', consent: boolean, trainingConsent: boolean,
  externalVisionConsent: boolean, sessionId?: string, heightMm?: number,
): Promise<QualityDecision> {
  const form = new FormData()
  form.append('view', view)
  form.append('consent', String(consent))
  form.append('training_consent', String(trainingConsent))
  form.append('external_vision_consent', String(externalVisionConsent))
  form.append('file', image)
  if (sessionId) form.append('session_id', sessionId)
  if (heightMm) form.append('height_mm', String(heightMm))

  let response: Response
  try {
    response = await authenticatedFetch('/api/capture', { method: 'POST', body: form })
  } catch {
    throw networkError('/api/capture')
  }
  if (!response.ok) throw new Error(`Capture check failed (${response.status}): ${await response.text()}`)
  return await response.json()
}

export async function submitCaptureBatch(
  front: File, side: File, back: File, consent: boolean, trainingConsent: boolean,
  externalVisionConsent: boolean,
  sessionId?: string, heightMm?: number,
): Promise<{ captureSessionId: string; results: QualityDecision[] }> {
  const form = new FormData()
  form.append('front', front)
  form.append('side', side)
  form.append('back', back)
  form.append('consent', String(consent))
  form.append('training_consent', String(trainingConsent))
  form.append('external_vision_consent', String(externalVisionConsent))
  if (sessionId) form.append('session_id', sessionId)
  if (heightMm) form.append('height_mm', String(heightMm))
  let response: Response
  try {
    response = await authenticatedFetch('/api/captures', { method: 'POST', body: form })
  } catch {
    throw networkError('/api/captures')
  }
  if (!response.ok) throw new Error(`Capture check failed (${response.status}): ${await response.text()}`)
  return await response.json()
}

export async function submitMeasurementEstimate(
  front: File, side: File, back: File, heightMm: number, consent: boolean,
  externalVisionConsent: boolean, sessionId?: string,
  calibration?: { kind: CalibrationKind; file: File },
): Promise<CircumferenceEstimate> {
  const form = new FormData()
  form.append('front', front)
  form.append('side', side)
  form.append('back', back)
  form.append('height_mm', String(heightMm))
  form.append('consent', String(consent))
  form.append('external_vision_consent', String(externalVisionConsent))
  if (sessionId) form.append('session_id', sessionId)
  if (calibration) {
    form.append('calibration_kind', calibration.kind)
    form.append('calibration_reference', calibration.file)
  }
  let response: Response
  try {
    response = await authenticatedFetch('/api/measurement-estimates', { method: 'POST', body: form })
  } catch {
    throw networkError('/api/measurement-estimates')
  }
  if (!response.ok) throw new Error(`Measurement estimate failed (${response.status}): ${await response.text()}`)
  return await response.json()
}

export async function deleteCaptureSession(sessionId: string): Promise<void> {
  let response: Response
  try {
    response = await authenticatedFetch(`/api/capture-sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    })
  } catch {
    throw networkError('/api/capture-sessions')
  }
  if (!response.ok) throw new Error(`Capture deletion failed (${response.status}): ${await response.text()}`)
}

/** POST a slow-turn video to the service and return its review decision. */
export async function submitTurnVideoCheck(file: File, consent: boolean, sessionId?: string, heightMm?: number): Promise<VideoDecision> {
  const form = new FormData()
  form.append('consent', String(consent))
  form.append('file', file)
  if (sessionId) form.append('session_id', sessionId)
  if (heightMm) form.append('height_mm', String(heightMm))

  let response: Response
  try {
    response = await authenticatedFetch('/api/turn-video', { method: 'POST', body: form })
  } catch {
    throw networkError('/api/turn-video')
  }
  if (!response.ok) throw new Error(`Video check failed (${response.status}): ${await response.text()}`)
  return (await response.json()) as VideoDecision
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const signedIn = await authClient.signIn.email({ email, password })
  if (signedIn.error) throw new Error(signedIn.error.message || 'Invalid email or password.')
  return loadAuthSession()
}

export async function signUp(name: string, email: string, password: string): Promise<AuthSession> {
  const created = await authClient.signUp.email({ name, email, password })
  if (created.error) throw new Error(created.error.message || 'Could not create account.')
  return loadAuthSession()
}

export async function loadAuthSession(): Promise<AuthSession> {
  const token = await bearerToken()
  const response = await fetch(apiUrl('/api/auth/me'), { headers: { Authorization: `Bearer ${token}` } })
  if (!response.ok) throw new Error('Could not load your VisionFit account.')
  return { user: await response.json() }
}

export async function logout(_token?: string): Promise<void> {
  await authClient.signOut()
}

export async function getMeasurementDefinitions(): Promise<MeasurementDefinitionDto[]> {
  const response = await fetch(apiUrl('/api/measurements/definitions'))
  if (!response.ok) throw new Error('Could not load measurement definitions.')
  return (await response.json()).definitions
}

export async function getMeasurementPaths(): Promise<MeasurementPathDto[]> {
  const response = await fetch(apiUrl('/api/admin/measurement-paths'), { headers: await authorization() })
  if (!response.ok) throw new Error(`Could not load measurement paths: ${await response.text()}`)
  return (await response.json()).paths
}

export async function saveMeasurementPathDraft(
  key: string,
  path: Pick<MeasurementPathDto, 'path' | 'closed' | 'orderedPoints' | 'segmentViews' | 'requiredViews' | 'calculationMethod'>,
): Promise<MeasurementPathDto> {
  const response = await fetch(apiUrl(`/api/admin/measurement-paths/${key}/draft`), {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...(await authorization()) },
    body: JSON.stringify({
      path: path.path, closed: path.closed, ordered_points: path.orderedPoints,
      segment_views: path.segmentViews,
      required_views: path.requiredViews, calculation_method: path.calculationMethod,
    }),
  })
  if (!response.ok) throw new Error(`Could not save path draft: ${await response.text()}`)
  return await response.json()
}

export async function publishMeasurementPath(key: string): Promise<MeasurementPathDto> {
  const response = await fetch(apiUrl(`/api/admin/measurement-paths/${key}/publish`), {
    method: 'POST', headers: await authorization(),
  })
  if (!response.ok) throw new Error(`Could not publish path: ${await response.text()}`)
  return await response.json()
}

export async function createMeasurementTable(subjectId: string, captureSessionId?: string, _token?: string): Promise<MeasurementTableDto> {
  const response = await fetch(apiUrl('/api/measurement-tables'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authorization()) },
    body: JSON.stringify({ subject_id: subjectId, capture_session_id: captureSessionId, unit: 'cm' }),
  })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error('Administrator access required.')
    throw new Error('Could not create the measurement table.')
  }
  return await response.json()
}

export async function getCustomers(): Promise<CustomerDto[]> {
  const response = await fetch(apiUrl('/api/admin/customers'), { headers: await authorization() })
  if (!response.ok) throw new Error('Could not load customers.')
  return (await response.json()).customers
}

export async function getAnalysisDecisions(): Promise<AnalysisDecisionDto[]> {
  const response = await fetch(apiUrl('/api/decisions?limit=20'), { headers: await authorization() })
  if (!response.ok) throw new Error('Could not load capture analyses.')
  return (await response.json()).records
}

export async function getCaptureSessions(): Promise<CaptureSessionSummaryDto[]> {
  const response = await fetch(apiUrl('/api/admin/capture-sessions'), { headers: await authorization() })
  if (!response.ok) throw new Error('Could not load capture sessions.')
  return (await response.json()).sessions
}

export async function getCaptureSession(sessionId: string): Promise<CaptureSessionDetailDto> {
  const response = await fetch(apiUrl(`/api/admin/capture-sessions/${sessionId}`), { headers: await authorization() })
  if (!response.ok) throw new Error('Could not load capture evidence.')
  return await response.json()
}

export async function getMeasurementAnalysis(sessionId: string): Promise<MeasurementReadinessDto> {
  const response = await fetch(apiUrl(`/api/admin/capture-sessions/${sessionId}/measurement-analysis`), { headers: await authorization() })
  if (!response.ok) throw new Error('Could not load measurement analysis.')
  return await response.json()
}

export async function updateMeasurementValue(
  tableId: string,
  key: string,
  value: number,
  status: 'estimated' | 'reviewed',
  sourceViews: string[],
  confidence?: number,
): Promise<MeasurementTableDto> {
  const response = await fetch(apiUrl(`/api/measurement-tables/${tableId}/measurements/${key}?unit=cm`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await authorization()) },
    body: JSON.stringify({
      value,
      unit: 'cm',
      status,
      method: status === 'reviewed' ? 'admin_review' : 'admin_estimate',
      source_views: sourceViews,
      confidence: status === 'estimated' ? (confidence ?? 0.5) : confidence,
    }),
  })
  if (!response.ok) throw new Error(`Could not save ${key}: ${await response.text()}`)
  return await response.json()
}
