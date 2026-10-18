import { useMemo, useState } from 'react'
import { CheckCircle2, Clock, ListTodo, Plus, Search, Trash2, Edit2 } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Segmented,
  Skeleton,
  Stat,
  useToast,
} from '@/components/ui'
import { useDebounced, useMutation, useQuery } from '@/lib/hooks'
import { formatDate } from '@/lib/format'
import { itemsApi } from './api'
import { ItemModal } from './ItemModal'
import type { Item, ItemCreate, ItemStatus, ItemUpdate } from '@/types'

const statusTones: Record<ItemStatus, 'warning' | 'info' | 'success'> = {
  todo: 'warning',
  in_progress: 'info',
  done: 'success',
}

const statusLabels: Record<ItemStatus, string> = {
  todo: 'В планах',
  in_progress: 'В процессе',
  done: 'Готово',
}

export function ItemsPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<Item | null>(null)

  const debouncedSearch = useDebounced(search, 300)
  const toast = useToast()

  const { data, loading, error, refetch } = useQuery(
    () =>
      itemsApi.list({
        q: debouncedSearch || undefined,
        status: statusFilter !== 'all' ? (statusFilter as ItemStatus) : undefined,
      }),
    [debouncedSearch, statusFilter]
  )

  const createMutation = useMutation(itemsApi.create)
  const updateMutation = useMutation((args: { id: number; data: ItemUpdate }) =>
    itemsApi.update(args.id, args.data)
  )
  const deleteMutation = useMutation(itemsApi.delete)

  const items = data?.items || []

  const stats = useMemo(() => {
    const total = data?.total ?? 0
    const inProgress = items.filter((i) => i.status === 'in_progress').length
    const done = items.filter((i) => i.status === 'done').length
    return { total, inProgress, done }
  }, [items, data?.total])

  const handleCreateOrUpdate = async (formData: ItemCreate) => {
    if (editingItem) {
      await updateMutation.mutate({ id: editingItem.id, data: formData })
      toast('Задача обновлена', 'success')
    } else {
      await createMutation.mutate(formData)
      toast('Задача успешно создана!', 'success')
    }
    refetch()
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('Точно удалить эту задачу?')) return
    try {
      await deleteMutation.mutate(id)
      toast('Задача удалена', 'info')
      refetch()
    } catch {
      toast('Не удалось удалить задачу', 'error')
    }
  }

  const handleStatusCycle = async (item: Item) => {
    const cycle: Record<ItemStatus, ItemStatus> = {
      todo: 'in_progress',
      in_progress: 'done',
      done: 'todo',
    }
    const nextStatus = cycle[item.status]
    await updateMutation.mutate({ id: item.id, data: { status: nextStatus } })
    refetch()
  }

  return (
    <div className="stack" style={{ gap: 24 }}>
      <PageHeader
        title="Задачи и MVP-бэклог"
        description="Рабочий пример CRUD-фичи с пагинацией, полнотекстовым поиском, фильтрами и валидацией данных через FastAPI + SQLAlchemy."
        actions={
          <Button
            variant="primary"
            icon={<Plus />}
            onClick={() => {
              setEditingItem(null)
              setModalOpen(true)
            }}
          >
            Новая задача
          </Button>
        }
      />

      {/* Верхние метрики проекта */}
      <div className="grid" style={{ '--min': '220px' } as any}>
        <Card>
          <Stat icon={<ListTodo />} label="Всего в базе" value={stats.total} />
        </Card>
        <Card>
          <Stat icon={<Clock />} label="Сейчас в работе" value={stats.inProgress} />
        </Card>
        <Card>
          <Stat icon={<CheckCircle2 />} label="Выполнено" value={stats.done} />
        </Card>
      </div>

      {/* Панель поиска и фильтрации */}
      <Card style={{ padding: '14px 18px' }}>
        <div className="row between" style={{ gap: 16 }}>
          <div style={{ flex: '1 1 280px', maxWidth: 440 }}>
            <Input
              icon={<Search />}
              placeholder="Поиск по названию или описанию..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <Segmented
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: 'all', label: 'Все' },
              { value: 'todo', label: 'В планах' },
              { value: 'in_progress', label: 'В процессе' },
              { value: 'done', label: 'Готово' },
            ]}
          />
        </div>
      </Card>

      {/* Список задач */}
      {loading && !data ? (
        <div className="grid">
          <Skeleton height={140} />
          <Skeleton height={140} />
          <Skeleton height={140} />
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : items.length === 0 ? (
        <EmptyState
          title="Задач не найдено"
          description={search ? 'Попробуйте изменить поисковый запрос' : 'Создайте первую задачу для проверки работы БД!'}
          action={
            <Button
              variant="primary"
              icon={<Plus />}
              onClick={() => {
                setEditingItem(null)
                setModalOpen(true)
              }}
            >
              Создать задачу
            </Button>
          }
        />
      ) : (
        <div className="grid" style={{ '--min': '320px' } as any}>
          {items.map((item) => (
            <Card key={item.id} className="stack" style={{ gap: 12, justifyContent: 'space-between' }}>
              <div>
                <div className="row between" style={{ marginBottom: 8, alignItems: 'flex-start' }}>
                  <button
                    type="button"
                    onClick={() => handleStatusCycle(item)}
                    title="Нажмите, чтобы переключить статус"
                    style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
                  >
                    <Badge tone={statusTones[item.status]} dot>
                      {statusLabels[item.status]}
                    </Badge>
                  </button>
                  <span className="small faint">{formatDate(item.created_at)}</span>
                </div>

                <h3 style={{ fontSize: '1.05rem', fontWeight: 650, marginBottom: 6 }}>
                  {item.title}
                </h3>

                {item.description ? (
                  <p className="small muted" style={{ whiteSpace: 'pre-line' }}>
                    {item.description}
                  </p>
                ) : (
                  <p className="small faint" style={{ fontStyle: 'italic' }}>
                    Без описания
                  </p>
                )}
              </div>

              <div
                className="row between"
                style={{
                  borderTop: '1px solid var(--border)',
                  paddingTop: 10,
                  marginTop: 6,
                }}
              >
                <span className="small faint mono">id: #{item.id}</span>
                <div className="row" style={{ gap: 6 }}>
                  <Button
                    variant="ghost"
                    size="sm"
                    iconOnly
                    icon={<Edit2 size={15} />}
                    onClick={() => {
                      setEditingItem(item)
                      setModalOpen(true)
                    }}
                    aria-label="Редактировать"
                  />
                  <Button
                    variant="danger"
                    size="sm"
                    iconOnly
                    icon={<Trash2 size={15} />}
                    onClick={() => handleDelete(item.id)}
                    aria-label="Удалить"
                  />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ItemModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        item={editingItem}
        onSubmit={handleCreateOrUpdate}
      />
    </div>
  )
}
