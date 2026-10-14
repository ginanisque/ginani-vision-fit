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
        <li>Your photos and measurements are used only to build your measurement profile.</li>
        <li>Captures stay private to this fitting session.</li>
        <li>You can request deletion of your body images after measurement extraction.</li>
      </ul>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.agreed}
          onChange={(e) => onChange({ ...consent, agreed: e.target.checked })}
        />
        <span>I consent to my body photos being processed for measurement extraction.</span>
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={consent.acknowledged}
          onChange={(e) => onChange({ ...consent, acknowledged: e.target.checked })}
        />
        <span>I understand why captures are needed and how they will be handled.</span>
      </label>
      <div className="actions">
        <button className="primary" disabled={!canContinue} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
