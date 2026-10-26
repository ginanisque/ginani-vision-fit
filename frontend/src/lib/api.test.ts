import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { QualityDecision, VideoDecision } from '../types'
import { deleteCaptureSession, submitMeasurementEstimate, submitQualityCheck, submitTurnVideoCheck } from './api'
import { bearerToken } from './auth-client'

const decision: QualityDecision = {
  id: 'front-1',
  decision: 'proceed',
  view: 'front',
  imageFingerprint: { sha256: 'abc123' },
  dimensions: { width: 400, height: 300 },
  checks: {
    exposure: { status: 'pass', lumaMean: 128, darkClipFraction: 0, brightClipFraction: 0 },
    blur: { status: 'pass', laplacianVariance: 200 },
  },
  reasons: [],
  thresholds: { laplacianVarianceMin: 100 },
  provisionalThresholds: true,
  scope: 'exposure and blur only',
  checkedAt: '2026-10-12T00:00:00Z',
}

function fakeResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

beforeEach(() => {
  vi.mocked(bearerToken).mockResolvedValue('api-test-token')
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('submitQualityCheck', () => {
  it('posts the file and view and returns the decision', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse(decision))
    const file = new File(['fake'], 'front.png', { type: 'image/png' })

    const result = await submitQualityCheck(file, 'front', true, { fetchFn })

    expect(result).toEqual(decision)
    expect(fetchFn).toHaveBeenCalledWith(
      '/api/quality',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchFn.mock.calls[0][1].headers).toHaveProperty('Authorization')
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('view')).toBe('front')
    expect(body.get('consent')).toBe('true')
    expect(body.get('file')).toBe(file)
  })

  it('throws on a non-ok response', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ detail: 'bad' }, false, 400))
    await expect(
      submitQualityCheck(new File(['x'], 'a.png', { type: 'image/png' }), 'front', true, { fetchFn }),
    ).rejects.toThrow(/Quality check failed/)
  })
})

describe('submitTurnVideoCheck', () => {
  const decision: VideoDecision = {
    id: 'v1',
    view: 'turn',
    decision: 'review',
    durationSeconds: 10,
    samples: [{ timeSeconds: 1, quality: 'pass', reasons: [] }],
    reasons: ['Confirm a full turn.'],
    scope: 'sample quality only',
  }

  it('posts the video and consent and returns the decision', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse(decision))
    vi.stubGlobal('fetch', fetchFn)
    const file = new File(['video'], 'turn.webm', { type: 'video/webm' })

    const result = await submitTurnVideoCheck(file, true, 'session-1', 1650, true)

    expect(result).toEqual(decision)
    expect(bearerToken).toHaveBeenCalledOnce()
    expect(fetchFn).toHaveBeenCalledWith('/api/turn-video', expect.objectContaining({
      method: 'POST',
      headers: { Authorization: 'Bearer api-test-token' },
    }))
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('consent')).toBe('true')
    expect(body.get('session_id')).toBe('session-1')
    expect(body.get('height_mm')).toBe('1650')
    expect(body.get('training_consent')).toBe('true')
    expect(body.get('file')).toBe(file)
  })

  it('turns a network rejection into an actionable message', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchFn)

    await expect(
      submitTurnVideoCheck(new File(['video'], 'turn.webm', { type: 'video/webm' }), true),
    ).rejects.toThrow(/Could not reach the analysis service/)
    expect(bearerToken).toHaveBeenCalledOnce()
    expect(fetchFn).toHaveBeenCalledWith('/api/turn-video', expect.objectContaining({
      headers: { Authorization: 'Bearer api-test-token' },
    }))
  })

  it('refreshes a rejected cached token and retries the upload once', async () => {
    vi.mocked(bearerToken)
      .mockResolvedValueOnce('expired-token')
      .mockResolvedValueOnce('fresh-token')
    const fetchFn = vi.fn()
      .mockResolvedValueOnce(fakeResponse({ detail: 'expired' }, false, 401))
      .mockResolvedValueOnce(fakeResponse(decision))
    vi.stubGlobal('fetch', fetchFn)

    const result = await submitTurnVideoCheck(
      new File(['video'], 'turn.webm', { type: 'video/webm' }), true,
    )

    expect(result).toEqual(decision)
    expect(bearerToken).toHaveBeenNthCalledWith(1, false)
    expect(bearerToken).toHaveBeenNthCalledWith(2, true)
    expect(fetchFn).toHaveBeenNthCalledWith(1, '/api/turn-video', expect.objectContaining({
      headers: { Authorization: 'Bearer expired-token' },
    }))
    expect(fetchFn).toHaveBeenNthCalledWith(2, '/api/turn-video', expect.objectContaining({
      headers: { Authorization: 'Bearer fresh-token' },
    }))
  })
})

describe('submitMeasurementEstimate', () => {
  it('sends the selected calibration reference separately from the clean front image', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ status: 'review_required' }))
    vi.stubGlobal('fetch', fetchFn)
    const front = new File(['front'], 'front.png', { type: 'image/png' })
    const side = new File(['side'], 'side.png', { type: 'image/png' })
    const back = new File(['back'], 'back.png', { type: 'image/png' })
    const reference = new File(['a4'], 'a4.png', { type: 'image/png' })

    await submitMeasurementEstimate(front, side, back, 1650, true, true, 'session-1', {
      kind: 'a4', file: reference,
    })

    describe('deleteCaptureSession', () => {
      it('sends an authenticated delete request for the selected capture', async () => {
        const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ deleted: true }))
        vi.stubGlobal('fetch', fetchFn)

        await deleteCaptureSession('session-1')

        expect(fetchFn).toHaveBeenCalledWith('/api/capture-sessions/session-1', expect.objectContaining({
          method: 'DELETE',
          headers: { Authorization: '******' },
        }))
      })
    })

    expect(bearerToken).toHaveBeenCalledOnce()
    const request = fetchFn.mock.calls[0][1]
    expect(request.headers).toEqual({ Authorization: 'Bearer api-test-token' })
    const body = request.body as FormData
    expect(body.get('front')).toBe(front)
    expect(body.get('external_vision_consent')).toBe('true')
    expect(body.get('calibration_kind')).toBe('a4')
    expect(body.get('calibration_reference')).toBe(reference)
  })
})
