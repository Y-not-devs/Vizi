import { useState, type ReactNode } from 'react'
import {
  Bot,
  ExternalLink,
  FileText,
  Layers,
  LogIn,
  LogOut,
  User,
  Zap,
} from 'lucide-react'
import { Badge, Button } from '@/components/ui'
import { useAppMeta } from '@/context/MetaContext'
import { useAuth } from '@/features/auth/AuthContext'
import { AuthModal } from '@/features/auth/AuthModal'
import './layout.css'

export type TabKey = 'items' | 'ai' | 'uploads'

interface AppLayoutProps {
  currentTab: TabKey
  onSelectTab: (tab: TabKey) => void
  children: ReactNode
}

export function AppLayout({ currentTab, onSelectTab, children }: AppLayoutProps) {
  const { meta, healthy } = useAppMeta()
  const { user, logout } = useAuth()
  const [authOpen, setAuthOpen] = useState(false)

  const navItems: { key: TabKey; label: string; icon: ReactNode; badge?: string }[] = [
    { key: 'items', label: 'Задачи и MVP', icon: <Layers size={18} /> },
    { key: 'ai', label: 'AI Чат', icon: <Bot size={18} />, badge: meta?.features.ai ? 'on' : undefined },
    { key: 'uploads', label: 'Файлы', icon: <FileText size={18} /> },
  ]

  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        <div>
          <div className="app-brand">
            <div className="app-brand__icon">
              <Zap size={20} />
            </div>
            <div>
              <div className="app-brand__title">{meta?.app_name || 'Launchpad'}</div>
              <div className="small faint">v0.1.0 • {meta?.environment || 'dev'}</div>
            </div>
          </div>

          <nav className="app-nav">
            {navItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`app-nav__item ${currentTab === item.key ? 'app-nav__item--active' : ''}`}
                onClick={() => onSelectTab(item.key)}
                style={{ width: '100%', border: 'none', background: 'none', textAlign: 'left', cursor: 'pointer' }}
              >
                {item.icon}
                <span className="grow">{item.label}</span>
                {item.badge && <Badge tone="accent">{item.badge}</Badge>}
              </button>
            ))}

            <a
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
              className="app-nav__item"
              style={{ marginTop: 8 }}
            >
              <ExternalLink size={18} />
              <span className="grow">FastAPI Docs</span>
              <span className="faint small">Swagger</span>
            </a>
          </nav>
        </div>

        <div className="app-sidebar__bottom">
          {/* Статус бэкенда */}
          <div className="row between" style={{ fontSize: '0.82rem' }}>
            <span className="muted">Бэкенд:</span>
            {healthy === null ? (
              <Badge tone="neutral">Проверка...</Badge>
            ) : healthy ? (
              <Badge tone="success" dot>Online</Badge>
            ) : (
              <Badge tone="danger" dot>Offline</Badge>
            )}
          </div>

          {/* Авторизация / Пользователь */}
          {user ? (
            <div
              className="row between"
              style={{
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
              }}
            >
              <div className="row" style={{ gap: 8, minWidth: 0 }}>
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: 'var(--accent-soft)',
                    display: 'grid',
                    placeItems: 'center',
                    color: 'var(--accent)',
                    flexShrink: 0,
                  }}
                >
                  <User size={14} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div className="small mono" style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {user.name || user.email.split('@')[0]}
                  </div>
                  <div className="faint small" style={{ fontSize: '0.72rem' }}>
                    {user.email}
                  </div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                iconOnly
                icon={<LogOut size={14} />}
                onClick={logout}
                aria-label="Выйти"
              />
            </div>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              icon={<LogIn size={15} />}
              onClick={() => setAuthOpen(true)}
              style={{ width: '100%' }}
            >
              Войти в систему
            </Button>
          )}

          <div className="small faint" style={{ textAlign: 'center', fontSize: '0.75rem' }}>
            Создано для хакатонов с ❤️
          </div>
        </div>
      </aside>

      <main className="app-main">{children}</main>

      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
    </div>
  )
}
