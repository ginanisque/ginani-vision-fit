export type HeightUnit = 'cm' | 'in'

export type Step = 'consent' | 'height' | 'front' | 'side' | 'review'

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
  view: 'front' | 'side'
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
}

export interface TurnCoverage {
  status: 'complete' | 'incomplete' | 'unknown'
  seenViews: string[]
  missingViews: string[]
  orientations: Array<{ timeSeconds: number; orientation: string }>
  method: string
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
}
