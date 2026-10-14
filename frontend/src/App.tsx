import { useMemo, useState } from 'react'
import type { ConsentState, HeightUnit, QualityDecision, Step } from './types'
import { submitCaptureCheck } from './lib/api'
import { validateHeight } from './lib/flow'
import { ConsentStep } from './components/ConsentStep'
import { HeightStep } from './components/HeightStep'
import { ImageSelectStep } from './components/ImageSelectStep'
import { QualityResult } from './components/QualityResult'
import { TurnVideo } from './components/TurnVideo'
import { DecisionLog } from './components/DecisionLog'

interface ImageSlot {
  file: File | null
  preview: string | null
}

export default function App() {
  const [step, setStep] = useState<Step>('consent')
  const [consent, setConsent] = useState<ConsentState>({ agreed: false, acknowledged: false })
  const [height, setHeight] = useState<{ value: string; unit: HeightUnit }>({ value: '', unit: 'cm' })
  const [front, setFront] = useState<ImageSlot>({ file: null, preview: null })
  const [side, setSide] = useState<ImageSlot>({ file: null, preview: null })
  const [lastRun, setLastRun] = useState<QualityDecision[]>([])
  const [log, setLog] = useState<QualityDecision[]>([])
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const heightError = useMemo(() => validateHeight(height.value, height.unit), [height])

  const handleImage = (view: 'front' | 'side', file: File | null) => {
    const old = view === 'front' ? front : side
    if (old.preview) URL.revokeObjectURL(old.preview)
    setLastRun([])
    const setter = view === 'front' ? setFront : setSide
    setter(file ? { file, preview: URL.createObjectURL(file) } : { file: null, preview: null })
  }

  const runChecks = async () => {
    if (!front.file || !side.file || !consent.agreed || !consent.acknowledged) return
    setChecking(true)
    setError(null)
    const next: QualityDecision[] = []
    try {
      const pairs: Array<[ImageSlot, 'front' | 'side']> = [
        [front, 'front'],
        [side, 'side'],
      ]
      for (const [slot, view] of pairs) {
        if (slot.file) {
          next.push(await submitCaptureCheck(slot.file, view, consent.agreed && consent.acknowledged))
        }
      }
      setLastRun(next)
      setLog((prev) => [...prev, ...next])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setChecking(false)
    }
  }

  const retake = (view: 'front' | 'side') => {
    setLastRun([])
    setError(null)
    setStep(view)
  }

  return (
    <div className="app">
      <header className="masthead">
        <span className="brand">Ginani VisionFit</span>
        <span className="tagline">Guided capture · {step}</span>
      </header>

      <main className="wizard">
        {step === 'consent' && (
          <ConsentStep consent={consent} onChange={setConsent} onContinue={() => setStep('height')} />
        )}
        {step === 'height' && (
          <HeightStep
            value={height.value}
            unit={height.unit}
            error={heightError}
            onChangeValue={(v) => setHeight((h) => ({ ...h, value: v }))}
            onChangeUnit={(u) => setHeight((h) => ({ ...h, unit: u }))}
            onBack={() => setStep('consent')}
            onContinue={() => setStep('front')}
          />
        )}
        {step === 'front' && (
          <ImageSelectStep
            view="front"
            preview={front.preview}
            onSelect={(f) => handleImage('front', f)}
            onBack={() => setStep('height')}
            onContinue={() => setStep('side')}
          />
        )}
        {step === 'side' && (
          <ImageSelectStep
            view="side"
            preview={side.preview}
            onSelect={(f) => handleImage('side', f)}
            onBack={() => setStep('front')}
            onContinue={() => setStep('review')}
          />
        )}
        {step === 'review' && (
          <QualityResult
            previews={{ front: front.preview, side: side.preview }}
            results={lastRun}
            checking={checking}
            error={error}
            onCheck={runChecks}
            onRetake={retake}
          />
        )}
      </main>

      {step === 'review' && consent.agreed && consent.acknowledged && (
        <TurnVideo consent={true} />
      )}
      <DecisionLog records={log} />
    </div>
  )
}
