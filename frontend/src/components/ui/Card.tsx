import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from '@/lib/format'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean
}

export function Card({ interactive, className, ...rest }: CardProps) {
  return <div className={cx('ui-card', interactive && 'ui-card--interactive', className)} {...rest} />
}

export function CardHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="ui-card__header">
      <div>
        <div className="ui-card__title">{title}</div>
        {subtitle && <div className="ui-card__subtitle">{subtitle}</div>}
      </div>
      {actions}
    </div>
  )
}

export function Stat({ icon, label, value }: { icon: ReactNode; label: ReactNode; value: ReactNode }) {
  return (
    <div className="ui-stat">
      <div className="ui-stat__icon">{icon}</div>
      <div>
        <div className="ui-stat__label">{label}</div>
        <div className="ui-stat__value">{value}</div>
      </div>
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ui-page-header fade-up">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  )
}
