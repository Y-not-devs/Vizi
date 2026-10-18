import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cx } from '@/lib/format'

interface FieldProps {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
}

function Field({ label, hint, error, id, children }: FieldProps & { id: string; children: ReactNode }) {
  return (
    <div className="ui-field">
      {label && (
        <label className="ui-field__label" htmlFor={id}>
          {label}
        </label>
      )}
      {children}
      {error ? <span className="ui-field__error">{error}</span> : hint && <span className="ui-field__hint">{hint}</span>}
    </div>
  )
}

export function Input({ label, hint, error, icon, className, id, ...rest }: FieldProps & InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  const autoId = useId()
  const inputId = id ?? autoId
  const input = <input id={inputId} className={cx('ui-input', className)} {...rest} />
  return (
    <Field label={label} hint={hint} error={error} id={inputId}>
      {icon ? (
        <div className="ui-input-wrap">
          {icon}
          {input}
        </div>
      ) : (
        input
      )}
    </Field>
  )
}

export function Textarea({ label, hint, error, className, id, ...rest }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <Field label={label} hint={hint} error={error} id={inputId}>
      <textarea id={inputId} className={cx('ui-input', className)} {...rest} />
    </Field>
  )
}

export function Select({
  label,
  hint,
  error,
  options,
  className,
  id,
  ...rest
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <Field label={label} hint={hint} error={error} id={inputId}>
      <select id={inputId} className={cx('ui-input', className)} {...rest}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

/** Переключатель-табы: фильтры, режимы и т.п. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: ReactNode }[]
}) {
  return (
    <div className="ui-segmented" role="group">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
