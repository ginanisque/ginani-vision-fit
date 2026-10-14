import type { HeightUnit } from '../types'

interface Props {
  value: string
  unit: HeightUnit
  error: string | null
  onChangeValue: (value: string) => void
  onChangeUnit: (unit: HeightUnit) => void
  onBack: () => void
  onContinue: () => void
}

export function HeightStep({
  value,
  unit,
  error,
  onChangeValue,
  onChangeUnit,
  onBack,
  onContinue,
}: Props) {
  const canContinue = Boolean(error === null && value.trim() !== '')
  return (
    <section className="step">
      <h1>Your height</h1>
      <p>Height is the reference we will use for scale in later measurement milestones.</p>
      <div className="field-row">
        <input
          type="number"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChangeValue(e.target.value)}
          placeholder="e.g. 165"
          aria-label="Height"
        />
        <select
          value={unit}
          onChange={(e) => onChangeUnit(e.target.value as HeightUnit)}
          aria-label="Unit"
        >
          <option value="cm">cm</option>
          <option value="in">in</option>
        </select>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="secondary" onClick={onBack}>
          Back
        </button>
        <button className="primary" disabled={!canContinue} onClick={onContinue}>
          Continue
        </button>
      </div>
    </section>
  )
}
