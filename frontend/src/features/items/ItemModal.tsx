import { useEffect, useState } from 'react'
import { Button, Input, Modal, Select, Textarea } from '@/components/ui'
import type { Item, ItemCreate, ItemStatus } from '@/types'

interface ItemModalProps {
  open: boolean
  onClose: () => void
  item?: Item | null
  onSubmit: (data: ItemCreate) => Promise<void>
}

const statusOptions: { value: ItemStatus; label: string }[] = [
  { value: 'todo', label: 'В планах (todo)' },
  { value: 'in_progress', label: 'В процессе (in_progress)' },
  { value: 'done', label: 'Готово (done)' },
]

export function ItemModal({ open, onClose, item, onSubmit }: ItemModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<ItemStatus>('todo')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (item) {
      setTitle(item.title)
      setDescription(item.description || '')
      setStatus(item.status)
    } else {
      setTitle('')
      setDescription('')
      setStatus('todo')
    }
    setError(null)
  }, [item, open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      setError('Заголовок обязателен')
      return
    }

    setLoading(true)
    setError(null)
    try {
      await onSubmit({ title: title.trim(), description: description.trim(), status })
      onClose()
    } catch (err: any) {
      setError(err.message || 'Ошибка при сохранении')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={item ? 'Редактировать задачу' : 'Новая задача'}
    >
      <form onSubmit={handleSubmit} className="stack">
        {error && <div className="ui-field__error">{error}</div>}

        <Input
          label="Заголовок"
          placeholder="Например: Собрать прототип лендинга"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <Textarea
          label="Описание"
          placeholder="Краткие детали, ссылки или требования..."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <Select
          label="Статус"
          value={status}
          onChange={(e) => setStatus(e.target.value as ItemStatus)}
          options={statusOptions}
        />

        <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" loading={loading}>
            {item ? 'Сохранить' : 'Создать'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
