import type { ConsentState } from '../types'

interface Props {
  consent: ConsentState
  onChange: (next: ConsentState) => void
  onContinue: () => void
}

export function ConsentStep({ consent, onChange, onContinue }: Props) {
  const canContinue = consent.agreed && consent.acknowledged
  return (
    <section className="step">
      <h1>Consent &amp; privacy</h1>
      <p>Before we begin, please confirm you understand how your captures will be used.</p>
      <ul className="privacy-list">
        <li>Your slow-turn video or optional photos and measurements are used to build your measurement profile.</li>
        <li>Captures are stored privately and are never sold or shared publicly.</li>
        <li>Capture media and linked measurement results are automatically deleted after 30 days. You can delete them sooner after submitting a capture.</li>
        <li>Roboflow keypoint detection is not used by the slow-turn estimate path. Still photos are sent to Roboflow only if you separately opt in below.</li>
      </ul>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.agreed}
          onChange={(e) => onChange({ ...consent, agreed: e.target.checked })}
        />
        <span>I consent to my body video or photos being processed for measurement estimation.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.acknowledged}
          onChange={(e) => onChange({ ...consent, acknowledged: e.target.checked })}
        />
        <span>I understand why captures are needed and how they will be handled.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.externalVision}
          onChange={(e) => onChange({ ...consent, externalVision: e.target.checked })}
        />
        <span>Optional: I consent to sending still capture photos to Roboflow for tailoring-keypoint detection.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.training}
          onChange={(e) => onChange({ ...consent, training: e.target.checked })}
        />
        <span>Optional: I also consent to my capture images being used to train the measurement model.</span>
      </label>
      <div className="actions">
        <button className="primary" disabled={!canContinue} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
