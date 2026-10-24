import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
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

async function reachReview(user: ReturnType<typeof userEvent.setup>, container: HTMLElement) {
  await user.click(screen.getByLabelText(/consent to my body photos/i))
  await user.click(screen.getByLabelText(/understand why captures/i))
  await user.click(screen.getByRole('button', { name: /continue/i }))

  await user.type(screen.getByLabelText(/height/i), '165')
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
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('gates the consent step', async () => {
    const user = userEvent.setup()
    render(<App />)

    const continueBtn = screen.getByRole('button', { name: /continue/i })
    expect(continueBtn).toBeDisabled()

    await user.click(screen.getByLabelText(/consent to my body photos/i))
    expect(continueBtn).toBeDisabled()

    await user.click(screen.getByLabelText(/understand why captures/i))
    expect(continueBtn).toBeEnabled()
  })

  it('requests recapture when an image fails quality', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(makeDecision('front', 'recapture')))
      .mockResolvedValueOnce(okResponse(makeDecision('side', 'proceed')))
      .mockResolvedValueOnce(okResponse(makeDecision('back', 'proceed')))
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
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okResponse(makeDecision('front', 'proceed')))
      .mockResolvedValueOnce(okResponse(makeDecision('side', 'proceed')))
      .mockResolvedValueOnce(okResponse(makeDecision('back', 'proceed')))
    vi.stubGlobal('fetch', fetchMock)

    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)

    await user.click(screen.getByRole('button', { name: /check quality/i }))

    expect(await screen.findByRole('heading', { name: /quality passed/i })).toBeInTheDocument()
    expect(screen.getByText(/image quality is acceptable/i)).toBeInTheDocument()
  })
  it('keeps uncertain capture evidence blocked and requests review', async () => {
    const result = makeDecision('front', 'review')
    result.reasons = ['Confirm cord placement.']
    result.evidence = [{ kind: 'cord-candidate', label: 'Possible cord', box: { x: 20, y: 100, width: 200, height: 5 } }]
    result.captureChecks = { posture: { status: 'unknown', method: 'human review required' } }
    const fetchMock = vi.fn().mockResolvedValueOnce(okResponse(result)).mockResolvedValueOnce(okResponse({ ...result, id: 'side-review', view: 'side' })).mockResolvedValueOnce(okResponse({ ...result, id: 'back-review', view: 'back' }))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    const { container } = render(<App />)
    await reachReview(user, container)
    await user.click(screen.getByRole('button', { name: /check quality/i }))
    expect(await screen.findByRole('heading', { name: /review needed/i })).toBeInTheDocument()
    expect(screen.queryByText(/image quality is acceptable/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText('front detected evidence').querySelector('rect')).toHaveAttribute('y', '100')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/capture')
    expect((fetchMock.mock.calls[0][1].body as FormData).get('consent')).toBe('true')
    await user.click(screen.getByRole('button', { name: /retake front/i }))
    expect(screen.getByRole('heading', { name: 'Front photo' })).toBeInTheDocument()
  })

  it('renders pose landmarks and posture orientation evidence', async () => {
    const result = makeDecision('front', 'review')
    result.reasons = ['Confirm posture.']
    result.evidence = [{ kind: 'pose-landmark', label: 'pose landmark: nose', box: { x: 50, y: 30, width: 2, height: 2 } }]
    result.captureChecks = { posture: { status: 'pass', method: 'MediaPipe Pose landmarks (33-point, provisional)', orientation: 'front', headToFeet: 'pass', postureQuality: 'pass', orientationMethod: 'shoulder/hip landmark geometry' } }
    const fetchMock = vi.fn().mockResolvedValueOnce(okResponse(result)).mockResolvedValueOnce(okResponse({ ...result, id: 'side-p', view: 'side' })).mockResolvedValueOnce(okResponse({ ...result, id: 'back-p', view: 'back' }))
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
