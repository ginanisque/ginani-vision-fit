import { useEffect, useMemo, useState } from 'react'
import type { AuthSession, ConsentState, HeightUnit, QualityDecision, Step } from './types'
import { loadAuthSession, logout, submitCaptureCheck } from './lib/api'
import { validateHeight } from './lib/flow'
import { ConsentStep } from './components/ConsentStep'
import { HeightStep } from './components/HeightStep'
import { ImageSelectStep } from './components/ImageSelectStep'
import { QualityResult } from './components/QualityResult'
import { TurnVideo } from './components/TurnVideo'
import { DecisionLog } from './components/DecisionLog'
import { LoginPanel } from './components/LoginPanel'
import { AdminPanel } from './components/AdminPanel'
import { LandingPage } from './components/LandingPage'

interface ImageSlot {
  file: File | null
  preview: string | null
}

export default function App() {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [page, setPage] = useState<'home' | 'capture' | 'admin'>('home')
  const [showLogin, setShowLogin] = useState(false)
  const [step, setStep] = useState<Step>('consent')
  const [consent, setConsent] = useState<ConsentState>({ agreed: false, acknowledged: false })
  const [height, setHeight] = useState<{ value: string; unit: HeightUnit }>({ value: '', unit: 'cm' })
  const [front, setFront] = useState<ImageSlot>({ file: null, preview: null })
  const [side, setSide] = useState<ImageSlot>({ file: null, preview: null })
  const [lastRun, setLastRun] = useState<QualityDecision[]>([])
  const [log, setLog] = useState<QualityDecision[]>([])
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [captureSessionId, setCaptureSessionId] = useState<string | undefined>()

  useEffect(() => {
    loadAuthSession().then(authenticated).catch(() => {
      setSession(null)
    })
  }, [])

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
    let activeSessionId = captureSessionId
    const numericHeight = Number(height.value) * (height.unit === 'in' ? 25.4 : 10)
    try {
      const pairs: Array<[ImageSlot, 'front' | 'side']> = [
        [front, 'front'],
        [side, 'side'],
      ]
      for (const [slot, view] of pairs) {
        if (slot.file) {
          const result = await submitCaptureCheck(
            slot.file, view, consent.agreed && consent.acknowledged,
            activeSessionId, numericHeight,
          )
          activeSessionId = result.captureSessionId ?? activeSessionId
          setCaptureSessionId(activeSessionId)
          next.push(result)
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

  const authenticated = (next: AuthSession) => {
    setSession(next)
    setShowLogin(false)
    if (next.user.role === 'admin') setPage('admin')
  }

  const signOut = async () => {
    if (session) await logout().catch(() => undefined)
    setSession(null)
    setPage('capture')
  }

  const startCapture = () => {
    setPage('capture')
    if (!session) setShowLogin(true)
  }

  return (
    <div className="app">
      <header className="masthead">
        <button className="brand brand-button" onClick={() => { setPage('home'); setShowLogin(false) }} aria-label="Ginani VisionFit home">
          <img src="/assets/Vision_Fit_Logo_512.png" alt="" />
          <span>Ginani VisionFit</span>
        </button>
        <nav className="main-nav" aria-label="Main navigation">
          <button className={page === 'home' ? 'nav-active' : ''} onClick={() => { setPage('home'); setShowLogin(false) }}>Home</button>
          <button className={page === 'capture' ? 'nav-active' : ''} onClick={startCapture}>Capture</button>
          {session?.user.role === 'admin' && <button className={page === 'admin' ? 'nav-active' : ''} onClick={() => setPage('admin')}>Admin</button>}
          {session ? <button onClick={signOut}>Sign out</button> : <button onClick={() => setShowLogin(true)}>Sign in</button>}
        </nav>
      </header>

      {session && <div className="account-strip"><span>{session.user.email}</span><span className="role-pill">{session.user.role}</span></div>}
      {showLogin && <LoginPanel onAuthenticated={authenticated} onCancel={() => setShowLogin(false)} />}

      {!showLogin && page === 'home' && <LandingPage onStart={startCapture} />}

      {!showLogin && page === 'admin' && session?.user.role === 'admin' && <AdminPanel />}

      {!showLogin && page === 'capture' && !session && <main className="login-panel step">
        <h1>Sign in to start a private capture</h1>
        <p className="muted">Your photos and video are stored privately and linked only to your VisionFit account.</p>
        <button className="primary" onClick={() => setShowLogin(true)}>Sign in or create account</button>
      </main>}

      {!showLogin && page === 'capture' && session && <><main className="wizard">
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

      {step === 'review' && consent.agreed && consent.acknowledged && lastRun.length === 2 && (
        <TurnVideo consent={true} sessionId={captureSessionId} />
      )}
      <DecisionLog records={log} />
      </>}
      <footer className="site-footer">
        <span>© {new Date().getFullYear()} Ginani VisionFit</span>
        <nav aria-label="Footer navigation"><button onClick={() => setPage('home')}>Home</button><a href="#faq" onClick={() => setPage('home')}>FAQ</a></nav>
      </footer>
    </div>
  )
}
