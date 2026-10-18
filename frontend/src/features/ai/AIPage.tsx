import { useState, useRef, useEffect } from 'react'
import { Bot, Send, Sparkles, User, AlertCircle, RefreshCw } from 'lucide-react'
import { Badge, Button, Card, PageHeader, Textarea, useToast } from '@/components/ui'
import { useAppMeta } from '@/context/MetaContext'
import { aiApi } from './api'
import type { ChatMessage } from '@/types'

const PRESETS = [
  { label: 'Хакатон-копирайтер', system: 'Ты — опытный маркетолог и питчер стартапов на хакатонах. Отвечай кратко, ёмко и убедительно.' },
  { label: 'Генератор идей', system: 'Ты — креативный директор. Придумывай нестандартные решения для проблем пользователя.' },
  { label: 'Технический архитектор', system: 'Ты — Senior Software Engineer. Предлагай архитектурные решения и структуры данных.' },
]

export function AIPage() {
  const { meta } = useAppMeta()
  const toast = useToast()

  const [systemPrompt, setSystemPrompt] = useState(PRESETS[0].system)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: 'Привет! Я готов помочь твоей команде с прототипом, генерацией контента или фичами проекта. Задай мне любой вопрос!',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastModel, setLastModel] = useState<string>('')
  const [isMock, setIsMock] = useState<boolean>(false)

  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = { role: 'user', content: text }
    const nextMessages = [...messages, userMsg]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)

    try {
      const res = await aiApi.chat(nextMessages, systemPrompt)
      setMessages([...nextMessages, { role: 'assistant', content: res.reply }])
      setLastModel(res.model)
      setIsMock(res.mock)
      if (res.mock) {
        toast('Ответ сформирован в mock-режиме (добавьте AI_API_KEY в .env для реальной LLM)', 'info')
      }
    } catch (err: any) {
      toast(err.message || 'Ошибка вызова AI', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = () => {
    setMessages([
      {
        role: 'assistant',
        content: 'История очищена. О чём подумаем дальше?',
      },
    ])
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <PageHeader
        title="AI Playground"
        description="Универсальный клиент для LLM: поддерживает OpenAI, Groq, OpenRouter, Together, а также локальные Ollama / LM Studio. Если ключ не задан, отвечает в mock-режиме."
        actions={
          <div className="row">
            {isMock ? (
              <Badge tone="warning" dot>Mock Mode (No Key)</Badge>
            ) : lastModel ? (
              <Badge tone="success" dot>{lastModel}</Badge>
            ) : (
              <Badge tone="accent">Готов к работе</Badge>
            )}
            <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={handleReset}>
              Очистить чат
            </Button>
          </div>
        }
      />

      {meta && !meta.features.ai && (
        <Card style={{ borderColor: 'hsl(38 95% 60% / 0.4)', background: 'hsl(38 95% 60% / 0.08)' }}>
          <div className="row" style={{ gap: 12 }}>
            <AlertCircle color="var(--warning)" />
            <div className="small">
              <strong>Внимание:</strong> модуль AI отключён в настройках (<code>ENABLE_AI=false</code>). Чтобы включить его, измените значение на <code>true</code> в <code>.env</code> и перезапустите сервер.
            </div>
          </div>
        </Card>
      )}

      {/* Выбор системного промпта */}
      <Card style={{ padding: '16px 20px' }}>
        <div className="stack" style={{ gap: 10 }}>
          <div className="row between">
            <span className="small muted"><strong>Роль и системный контекст:</strong></span>
            <div className="row" style={{ gap: 6 }}>
              {PRESETS.map((p) => (
                <Button
                  key={p.label}
                  variant={systemPrompt === p.system ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setSystemPrompt(p.system)}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
          <Textarea
            rows={2}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Задайте инструкции для поведения модели..."
            style={{ minHeight: 64, fontSize: '0.86rem' }}
          />
        </div>
      </Card>

      {/* Окно диалога */}
      <Card style={{ minHeight: 420, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: 24,
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
            maxHeight: '52vh',
          }}
        >
          {messages.map((m, idx) => {
            const isUser = m.role === 'user'
            return (
              <div
                key={idx}
                className="fade-up"
                style={{
                  display: 'flex',
                  gap: 12,
                  alignSelf: isUser ? 'flex-end' : 'flex-start',
                  maxWidth: '82%',
                  flexDirection: isUser ? 'row-reverse' : 'row',
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    display: 'grid',
                    placeItems: 'center',
                    flexShrink: 0,
                    background: isUser ? 'var(--accent)' : 'var(--surface-strong)',
                    color: 'white',
                    border: '1px solid var(--border)',
                  }}
                >
                  {isUser ? <User size={16} /> : <Bot size={16} />}
                </div>

                <div
                  style={{
                    padding: '12px 16px',
                    borderRadius: 14,
                    background: isUser ? 'var(--gradient)' : 'var(--surface-hover)',
                    color: 'var(--text)',
                    border: isUser ? 'none' : '1px solid var(--border)',
                    boxShadow: isUser ? 'var(--shadow-glow)' : 'none',
                    fontSize: '0.92rem',
                    lineHeight: 1.55,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {m.content}
                </div>
              </div>
            )
          })}

          {loading && (
            <div style={{ display: 'flex', gap: 12, alignSelf: 'flex-start', alignItems: 'center' }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  display: 'grid',
                  placeItems: 'center',
                  background: 'var(--surface-strong)',
                  border: '1px solid var(--border)',
                }}
              >
                <Bot size={16} />
              </div>
              <div className="small muted row" style={{ gap: 8 }}>
                <Sparkles size={16} className="gradient-text" />
                <span>Генерирую ответ...</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Инпут отправки */}
        <form
          onSubmit={handleSend}
          style={{
            borderTop: '1px solid var(--border)',
            padding: '14px 18px',
            background: 'var(--bg-elevated)',
            display: 'flex',
            gap: 12,
          }}
        >
          <input
            className="ui-input"
            placeholder="Спросите что-нибудь у модели..."
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            style={{ borderRadius: 'var(--radius)' }}
          />
          <Button
            type="submit"
            variant="primary"
            icon={<Send size={16} />}
            loading={loading}
            disabled={!input.trim()}
          >
            Отправить
          </Button>
        </form>
      </Card>
    </div>
  )
}
