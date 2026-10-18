import { useState, useRef } from 'react'
import { UploadCloud, File, Download, Image as ImageIcon, AlertCircle } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  useToast,
} from '@/components/ui'
import { useQuery } from '@/lib/hooks'
import { formatBytes, formatDate } from '@/lib/format'
import { useAppMeta } from '@/context/MetaContext'
import { uploadsApi } from './api'

export function UploadsPage() {
  const { meta } = useAppMeta()
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const { data: files, loading, error, refetch } = useQuery(
    uploadsApi.list,
    [],
    { enabled: meta?.features.uploads ?? true }
  )

  const handleUpload = async (file: globalThis.File) => {
    setUploading(true)
    try {
      await uploadsApi.upload(file)
      toast(`Файл «${file.name}» успешно загружен!`, 'success')
      refetch()
    } catch (err: any) {
      toast(err.message || 'Ошибка загрузки файла', 'error')
    } finally {
      setUploading(false)
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  const isImage = (type: string) => type.startsWith('image/')

  return (
    <div className="stack" style={{ gap: 24 }}>
      <PageHeader
        title="Загрузка файлов"
        description="Пример обработки мультимедиа: валидация размера, безопасное сохранение на сервере и прямая раздача файлов."
        actions={
          <Button
            variant="primary"
            icon={<UploadCloud />}
            loading={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            Выбрать файл
          </Button>
        }
      />

      <input
        type="file"
        ref={fileInputRef}
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleUpload(file)
          e.target.value = ''
        }}
      />

      {meta && !meta.features.uploads && (
        <Card style={{ borderColor: 'hsl(38 95% 60% / 0.4)', background: 'hsl(38 95% 60% / 0.08)' }}>
          <div className="row" style={{ gap: 12 }}>
            <AlertCircle color="var(--warning)" />
            <div className="small">
              <strong>Внимание:</strong> модуль загрузки файлов отключён (<code>ENABLE_UPLOADS=false</code>). Включите его в <code>.env</code> для работы с локальным диском.
            </div>
          </div>
        </Card>
      )}

      {/* Зона Drag & Drop */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        style={{
          border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border-strong)'}`,
          borderRadius: 'var(--radius-lg)',
          padding: '36px 20px',
          textAlign: 'center',
          background: dragOver ? 'var(--surface-hover)' : 'var(--surface)',
          transition: 'all var(--t-fast)',
          cursor: 'pointer',
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <div className="stack" style={{ alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              background: 'var(--accent-soft)',
              display: 'grid',
              placeItems: 'center',
              color: 'var(--accent-2)',
            }}
          >
            <UploadCloud size={26} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.05rem', marginBottom: 4 }}>
              Перетащите файл сюда или нажмите для выбора
            </h3>
            <p className="small muted">
              Поддерживаются изображения, аудио, PDF и документы до 10 МБ
            </p>
          </div>
        </div>
      </div>

      {/* Список файлов */}
      <div>
        <h2 style={{ fontSize: '1.2rem', marginBottom: 16 }}>Загруженные файлы</h2>

        {loading && !files ? (
          <div className="grid">
            <Skeleton height={100} />
            <Skeleton height={100} />
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : !files || files.length === 0 ? (
          <EmptyState
            title="Нет загруженных файлов"
            description="Загрузите первое изображение или документ, чтобы увидеть превью"
          />
        ) : (
          <div className="grid" style={{ '--min': '260px' } as any}>
            {files.map((f) => (
              <Card key={f.name} className="stack" style={{ gap: 12 }}>
                {isImage(f.content_type) ? (
                  <div
                    style={{
                      height: 140,
                      borderRadius: 'var(--radius-sm)',
                      overflow: 'hidden',
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                    }}
                  >
                    <img
                      src={f.url}
                      alt={f.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      loading="lazy"
                    />
                  </div>
                ) : (
                  <div
                    style={{
                      height: 80,
                      borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface-strong)',
                      display: 'grid',
                      placeItems: 'center',
                      color: 'var(--text-muted)',
                    }}
                  >
                    <File size={32} />
                  </div>
                )}

                <div className="stack" style={{ gap: 4 }}>
                  <div className="row between">
                    <span className="mono small" style={{ wordBreak: 'break-all', fontWeight: 600 }}>
                      {f.name.slice(0, 16)}...
                    </span>
                    <Badge tone="neutral">{formatBytes(f.size)}</Badge>
                  </div>
                  <span className="faint small">{formatDate(f.created_at)}</span>
                </div>

                <div className="row between" style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}>
                  <span className="faint small row" style={{ gap: 4 }}>
                    {isImage(f.content_type) ? <ImageIcon size={14} /> : <File size={14} />}
                    {f.content_type.split('/')[1] || 'file'}
                  </span>
                  <a href={f.url} download target="_blank" rel="noreferrer">
                    <Button variant="secondary" size="sm" icon={<Download size={14} />}>
                      Скачать
                    </Button>
                  </a>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
