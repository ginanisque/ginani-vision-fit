export type HeightUnit = 'cm' | 'in'

export interface AuthUser {
  email: string
  role: 'admin' | 'customer'
}

export interface AuthSession {
  user: AuthUser
}

export interface MeasurementDefinitionDto {
  key: string
  displayName: string
  scope: 'core' | 'future'
  category: string
  path: 'circumference' | 'straight' | 'surface'
  requiredViews: Array<'front' | 'side' | 'back'>
  requiredLandmarks: string[]
  calculation: string
}

export interface MeasurementRowDto extends MeasurementDefinitionDto {
  value: number | null
  unit: 'mm' | 'cm' | 'in'
  status: 'pending' | 'estimated' | 'reviewed' | 'unavailable'
  confidence: number | null
  requiresReview: boolean
}

export interface MeasurementTableDto {
  id: string
  subjectId: string
  registryVersion: string
  unit: 'mm' | 'cm' | 'in'
  rows: MeasurementRowDto[]
}

export interface CustomerDto {
  id: string
  email: string
  displayName: string | null
  role: 'admin' | 'customer'
  captureCount: number
  latestCaptureAt: string | null
}

export interface CaptureSessionSummaryDto {
  id: string
  customerId: string
  customerEmail: string
  customerName: string | null
  customerRole: 'admin' | 'customer'
  heightMm: number | null
  status: string
  views: string[]
  assetCount: number
  analysisCount: number
  consentedAt: string | null
  createdAt: string
  latestAnalysisAt: string | null
}

export interface CaptureAssetDto {
  id: string
  view: 'front' | 'side' | 'back' | 'turn'
  contentType: string
  byteSize: number
  widthPx: number | null
  heightPx: number | null
  durationSeconds: number | null
  capturedAt: string | null
  reviewUrl: string
}

export interface CaptureSessionDetailDto extends CaptureSessionSummaryDto {
  notes: string
  consentVersion: string | null
  assets: CaptureAssetDto[]
  analysisRuns: Array<{
    id: string
    modelName: string
    modelVersion: string
    status: string
    qualityDecision: Record<string, unknown> & { decision?: string; view?: string; reasons?: string[] }
    errorMessage: string | null
    createdAt: string
  }>
  landmarks: Array<{
    id: number
    assetId: string
    key: string
    x: number
    y: number
    visibility: number | null
    source: string
    manuallyAdjusted: boolean
  }>
}

export interface MeasurementReadinessDto {
  sessionId: string
  heightMm: number | null
  availableViews: string[]
  availableLandmarks: string[]
  readyCount: number
  blockedCount: number
  measurements: Array<MeasurementDefinitionDto & {
    status: 'ready_for_estimation' | 'blocked'
    missingViews: string[]
    missingLandmarks: string[]
    missingCalibration: boolean
    message: string
  }>
}

export interface AnalysisDecisionDto {
  id: string
  sessionId: string
  customerEmail: string
  status: string
  modelName: string
  modelVersion: string
  qualityDecision: { decision?: string; view?: string; reasons?: string[] }
  createdAt: string
}

export type Step = 'consent' | 'height' | 'front' | 'side' | 'back' | 'review'

export interface ConsentState {
  agreed: boolean
  acknowledged: boolean
}

export interface EvidenceBox {
  kind: string
  label: string
  box: { x: number; y: number; width: number; height: number }
}

export interface CaptureCheck {
  status: string
  method: string
}

export interface PostureCheck extends CaptureCheck {
  orientation?: string
  headToFeet?: string
  postureQuality?: string
  orientationMethod?: string
}

export interface CaptureChecks {
  framing?: CaptureCheck & { heightFraction?: number; edgeContact?: boolean }
  waistCord?: CaptureCheck & { widthFraction?: number }
  posture?: PostureCheck
  camera?: CaptureCheck
}

export interface QualityDecision {
  id: string
  decision: 'recapture' | 'proceed' | 'review'
  view: 'front' | 'side' | 'back'
  imageFingerprint: { sha256: string }
  dimensions: { width: number; height: number }
  checks: {
    exposure: {
      status: 'pass' | 'fail'
      lumaMean: number
      darkClipFraction: number
      brightClipFraction: number
    }
    blur: {
      status: 'pass' | 'fail'
      laplacianVariance: number
    }
  }
  reasons: string[]
  thresholds: Record<string, number>
  provisionalThresholds: boolean
  scope: string
  evidence?: EvidenceBox[]
  captureChecks?: CaptureChecks
  checkedAt: string
  captureSessionId?: string
  assetId?: string
  analysisRunId?: string
}

export interface CircumferenceEstimate {
  status: 'review_required'
  modelVersion: string
  registryVersion: string
  method: string
  warning: string
  orientations: { front: string; side: string; back: string }
  levels: { front: Record<string, number>; side: Record<string, number>; back: Record<string, number> }
  recommendedAction: string
  targetedManualCheck: { key: string; displayName: string; reason: string }
  trainingFeatures: { heightMm: number; rawMeasurementsMm: Record<string, number> }
  measurements: Array<{
    key: string
    displayName: string
    value: number
    unit: 'cm'
    rawValueMm: number
    uncertaintyMm: number
    confidence: number
    requiresReview: true
    sourceViews: Array<'front' | 'side' | 'back'>
    provenance: string
    evidence: Record<string, number>
  }>
}

export interface TurnCoverage {
  status: 'complete' | 'incomplete' | 'unknown'
  seenViews: string[]
  missingViews: string[]
  orientations: Array<{ timeSeconds: number; orientation: string }>
  method: string
  backMeasurements?: {
    status: 'experimental'
    method: string
    warning: string
    timeSeconds: number
    measurements: Array<{
      key: 'across_back' | 'nape_to_cb_waist'
      displayName: string
      value: number
      unit: 'cm'
      confidence: number
      requiresReview: true
    }>
  } | null
}

export interface VideoDecision {
  id: string
  view: 'turn'
  decision: 'recapture' | 'review'
  durationSeconds: number
  samples: Array<{timeSeconds: number; quality: 'pass' | 'fail'; reasons: string[]}>
  turnCoverage?: TurnCoverage
  reasons: string[]
  scope: string
  captureSessionId?: string
}
