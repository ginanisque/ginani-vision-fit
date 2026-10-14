import { describe, expect, it, vi } from 'vitest'
import type { QualityDecision, VideoDecision } from '../types'
import { submitQualityCheck, submitTurnVideoCheck } from './api'

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

describe('submitQualityCheck', () => {
  it('posts the file and view and returns the decision', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse(decision))
    const file = new File(['fake'], 'front.png', { type: 'image/png' })

    const result = await submitQualityCheck(file, 'front', { fetchFn })

    expect(result).toEqual(decision)
    expect(fetchFn).toHaveBeenCalledWith(
      '/api/quality',
      expect.objectContaining({ method: 'POST' }),
    )
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('view')).toBe('front')
    expect(body.get('file')).toBe(file)
  })

  it('throws on a non-ok response', async () => {
    const fetchFn = vi.fn().mockResolvedValue(fakeResponse({ detail: 'bad' }, false, 400))
    await expect(
      submitQualityCheck(new File(['x'], 'a.png', { type: 'image/png' }), 'front', { fetchFn }),
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

    const result = await submitTurnVideoCheck(file, true)

    expect(result).toEqual(decision)
    expect(fetchFn).toHaveBeenCalledWith('/api/turn-video', expect.objectContaining({ method: 'POST' }))
    const body = fetchFn.mock.calls[0][1].body as FormData
    expect(body.get('consent')).toBe('true')
    expect(body.get('file')).toBe(file)
    vi.unstubAllGlobals()
  })

  it('turns a network rejection into an actionable message', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchFn)

    await expect(
      submitTurnVideoCheck(new File(['video'], 'turn.webm', { type: 'video/webm' }), true),
    ).rejects.toThrow(/Could not reach the analysis service/)
    vi.unstubAllGlobals()
  })
})
