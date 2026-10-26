import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import * as api from './lib/api'
import type { QualityDecision } from './types'

function makeDecision(view: 'front' | 'side' | 'back', decision: 'recapture' | 'proceed' | 'review'): QualityDecision {
  return {
    id: `${view}-1`,
    decision,
    view,
    imageFingerprint: { sha256: 'abc123' },
    dimensions: { width: 400, height: 300 },
    checks: {
      exposure: { status: 'pass', lumaMean: 128, darkClipFraction: 0, brightClipFraction: 0 },
      blur: {
        status: decision === 'proceed' ? 'pass' : 'fail',
        laplacianVariance: decision === 'proceed' ? 200 : 10,
      },
    },
    reasons:
      decision === 'proceed'
        ? []
        : ['blurry: Laplacian variance 10.0 is below the provisional minimum 100.0'],
    thresholds: { laplacianVarianceMin: 100 },
    provisionalThresholds: true,
    scope: 'exposure and blur only',
    checkedAt: new Date().toISOString(),
  }
}

function okResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

const png = () => new File(['fake'], 'image.png', { type: 'image/png' })

async function reachReview(
  user: ReturnType<typeof userEvent.setup>, container: HTMLElement, externalVision = false,
) {
  await waitFor(() => expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument())
  await user.click(screen.getByRole('button', { name: /start visionfit/i }))
  await user.click(screen.getByLabelText(/consent to my body video or photos/i))
  await user.click(screen.getByLabelText(/understand why captures/i))
  if (externalVision) await user.click(screen.getByLabelText(/consent to sending still capture photos/i))
  await user.click(screen.getByRole('button', { name: /continue/i }))

  await user.type(screen.getByLabelText(/height/i), '165')
  await user.click(screen.getByRole('button', { name: /continue/i }))
  await user.click(screen.getByRole('button', { name: /use separate photos instead/i }))
  await user.click(screen.getByRole('button', { name: /continue/i }))

  const frontInput = container.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(frontInput, png())
  await user.click(screen.getByRole('button', { name: /continue/i }))

  const sideInput = container.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(sideInput, png())
  await user.click(screen.getByRole('button', { name: /continue/i }))

  const backInput = container.querySelector('input[type="file"]') as HTMLInputElement
  await user.upload(backInput, png())
  await user.click(screen.getByRole('button', { name: /continue/i }))
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.spyOn(api, 'loadAuthSession').mockResolvedValue({ user: { email: 'customer@example.test', role: 'customer' } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('gates the consent step', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /start visionfit/i }))

    const continueBtn = screen.getByRole('button', { name: /continue/i })
    expect(continueBtn).toBeDisabled()

    await user.click(screen.getByLabelText(/consent to my body video or photos/i))
    expect(continueBtn).toBeDisabled()

    await user.click(screen.getByLabelText(/understand why captures/i))
    expect(continueBtn).toBeEnabled()
  })

  it('defaults to slow-turn video and keeps still photos as an optional fallback', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /start visionfit/i }))
    await user.click(screen.getByLabelText(/consent to my body video or photos/i))
    await user.click(screen.getByLabelText(/understand why captures/i))
    await user.click(screen.getByRole('button', { name: /continue/i }))
    await user.type(screen.getByLabelText(/height/i), '165')
    await user.click(screen.getByRole('button', { name: /continue/i }))

    expect(screen.getByRole('heading', { name: /one slow-turn video/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/choose video/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /use separate photos instead/i }))
    expect(screen.getByRole('heading', { name: /optional scale reference/i })).toBeInTheDocument()
  })

  it('requests recapture when an image fails quality', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(okResponse({
      captureSessionId: 'session-1',
      results: [makeDecision('front', 'recapture'), makeDecision('side', 'proceed'), makeDecision('back', 'proceed')],
    }))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)

    await user.click(screen.getByRole('button', { name: /check quality/i }))

    expect(await screen.findByRole('heading', { name: /recapture needed/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retake front/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retake side/i })).not.toBeInTheDocument()
  })

  it('allows progression when all three images pass', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse({
        captureSessionId: 'session-1',
        results: [makeDecision('front', 'proceed'), makeDecision('side', 'proceed'), makeDecision('back', 'proceed')],
      }))
      .mockRejectedValueOnce(new TypeError('estimate unavailable'))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)

    await user.click(screen.getByRole('button', { name: /check quality/i }))

    expect(await screen.findByRole('heading', { name: /quality passed/i })).toBeInTheDocument()
    expect(screen.getByText(/image quality is acceptable/i)).toBeInTheDocument()
  })

  it('sends the provider-consent choice with capture and measurement requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse({
        captureSessionId: 'session-1',
        results: [makeDecision('front', 'proceed'), makeDecision('side', 'proceed'), makeDecision('back', 'proceed')],
      }))
      .mockResolvedValueOnce(okResponse({
        status: 'review_required', modelVersion: 'test', registryVersion: '2.1.0',
        method: 'test', warning: 'Review required', orientations: { front: 'front', side: 'side', back: 'back' },
        levels: { front: {}, side: {}, back: {} }, recommendedAction: 'Review',
        targetedManualCheck: { key: 'bust', displayName: 'Bust', reason: 'Check' },
        trainingFeatures: { heightMm: 1650, rawMeasurementsMm: {} }, measurements: [],
      }))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container, true)
    await user.click(screen.getByRole('button', { name: /check quality/i }))

    await screen.findByRole('heading', { name: /quality passed/i })
    expect((fetchMock.mock.calls[0][1].body as FormData).get('external_vision_consent')).toBe('true')
    expect((fetchMock.mock.calls[1][1].body as FormData).get('external_vision_consent')).toBe('true')
  })

  it('lets a customer delete their capture session and linked data', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(okResponse({
        captureSessionId: 'session-1',
        results: [makeDecision('front', 'proceed'), makeDecision('side', 'proceed'), makeDecision('back', 'proceed')],
      }))
      .mockResolvedValueOnce(okResponse({ deleted: true }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn().mockReturnValue(true))

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)
    await user.click(screen.getByRole('button', { name: /check quality/i }))
    await screen.findByRole('button', { name: /delete my capture data/i })
    await user.click(screen.getByRole('button', { name: /delete my capture data/i }))

    await screen.findByRole('heading', { name: /consent & privacy/i })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/capture-sessions/session-1')
    expect(fetchMock.mock.calls[1][1].method).toBe('DELETE')
  })
  it('keeps uncertain capture evidence blocked and requests review', async () => {
    const result = makeDecision('front', 'review')
    result.reasons = ['Confirm cord placement.']
    result.evidence = [{ kind: 'cord-candidate', label: 'Possible cord', box: { x: 20, y: 100, width: 200, height: 5 } }]
    result.captureChecks = { posture: { status: 'unknown', method: 'human review required' } }
    const fetchMock = vi.fn().mockResolvedValueOnce(okResponse({
      captureSessionId: 'session-1',
      results: [result, { ...result, id: 'side-review', view: 'side' }, { ...result, id: 'back-review', view: 'back' }],
    })).mockRejectedValueOnce(new TypeError('estimate unavailable'))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)
    await user.click(screen.getByRole('button', { name: /check quality/i }))
    expect(await screen.findByRole('heading', { name: /review needed/i })).toBeInTheDocument()
    expect(screen.queryByText(/image quality is acceptable/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText('front detected evidence').querySelector('rect')).toHaveAttribute('y', '100')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/captures')
    expect((fetchMock.mock.calls[0][1].body as FormData).get('consent')).toBe('true')
    await user.click(screen.getByRole('button', { name: /retake front/i }))
    expect(screen.getByRole('heading', { name: 'Front photo' })).toBeInTheDocument()
  })

  it('renders pose landmarks and posture orientation evidence', async () => {
    const result = makeDecision('front', 'review')
    result.reasons = ['Confirm posture.']
    result.evidence = [{ kind: 'pose-landmark', label: 'pose landmark: nose', box: { x: 50, y: 30, width: 2, height: 2 } }]
    result.captureChecks = { posture: { status: 'pass', method: 'MediaPipe Pose landmarks (33-point, provisional)', orientation: 'front', headToFeet: 'pass', postureQuality: 'pass', orientationMethod: 'shoulder/hip landmark geometry' } }
    const fetchMock = vi.fn().mockResolvedValueOnce(okResponse({
      captureSessionId: 'session-1',
      results: [result, { ...result, id: 'side-p', view: 'side' }, { ...result, id: 'back-p', view: 'back' }],
    })).mockRejectedValueOnce(new TypeError('estimate unavailable'))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)
    await user.click(screen.getByRole('button', { name: /check quality/i }))

    await screen.findByRole('heading', { name: /review needed/i })
    expect(screen.getByLabelText('front detected evidence').querySelector('circle')).toBeInTheDocument()
    expect(screen.getAllByText(/view front, head-to-feet pass/).length).toBeGreaterThan(0)
  })

})
