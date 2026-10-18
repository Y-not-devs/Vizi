import type { CSSProperties, ReactNode } from 'react'
import { AlertTriangle, Inbox } from 'lucide-react'
import { cx } from '@/lib/format'
import { Button } from './Button'

export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info'

export function Badge({ tone = 'neutral', dot, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return <span className={cx('ui-badge', `ui-badge--${tone}`, dot && 'ui-badge--dot')}>{children}</span>
}

export function Spinner({ size = 18 }: { size?: number }) {
  return <span className="ui-spinner" style={{ '--size': `${size}px` } as CSSProperties} aria-label="Загрузка" />
}

export function Skeleton({ height = 120, style }: { height?: number; style?: CSSProperties }) {
  return <div className="ui-skeleton" style={{ height, ...style }} />
}

export function EmptyState({
  icon = <Inbox />,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="ui-empty fade-up">
      <div className="ui-empty__icon">{icon}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="ui-empty ui-empty--error fade-up">
      <div className="ui-empty__icon">
        <AlertTriangle />
      </div>
      <h3>Что-то пошло не так</h3>
      <p>{error.message}</p>
      {onRetry && <Button onClick={onRetry}>Повторить</Button>}
    </div>
  )
}
