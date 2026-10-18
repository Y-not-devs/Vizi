import { useState } from 'react'
import { api } from '@/lib/api'
import { Button, Input, Modal, Segmented, useToast } from '@/components/ui'
import { useAuth } from './AuthContext'
import type { TokenResponse } from '@/types'

export function AuthModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { login } = useAuth()
  const toast = useToast()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      if (mode === 'login') {
        const res = await api.post<TokenResponse>('/auth/login', { email, password })
        login(res)
        toast('Успешный вход в систему!', 'success')
      } else {
        const res = await api.post<TokenResponse>('/auth/register', { email, password, name })
        login(res)
        toast('Аккаунт создан и выполнен вход!', 'success')
      }
      onClose()
    } catch (err: any) {
      setError(err.message || 'Ошибка авторизации')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === 'login' ? 'Вход в аккаунт' : 'Регистрация'}
    >
      <form onSubmit={handleSubmit} className="stack">
        <Segmented
          value={mode}
          onChange={(val) => {
            setMode(val)
            setError(null)
          }}
          options={[
            { value: 'login', label: 'Вход' },
            { value: 'register', label: 'Регистрация' },
          ]}
        />

        {error && (
          <div className="ui-field__error" style={{ fontSize: '0.86rem', marginTop: 4 }}>
            {error}
          </div>
        )}

        {mode === 'register' && (
          <Input
            label="Имя / Никнейм"
            placeholder="Алексей"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        )}

        <Input
          label="Email"
          type="email"
          required
          placeholder="team@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <Input
          label="Пароль"
          type="password"
          required
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <div style={{ marginTop: 12 }}>
          <Button type="submit" variant="primary" loading={loading} style={{ width: '100%' }}>
            {mode === 'login' ? 'Войти' : 'Создать аккаунт'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
