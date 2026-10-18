/**
 * HTTP-клиент взаимодействия с бэкендом ForteWatch (порт 8040)
 * Согласно ТЗ Datathon 26: POST /api/v1/analyze и GET /api/v1/jobs/{job_id}
 */

import type { AnalysisResponse, BackendMeta, JobStatus, Violation } from '@/types'
import { resolveRuleInfo } from './complianceRules'

const STORAGE_API_URL_KEY = 'fortewatch_api_url'
const STORAGE_API_KEY = 'fortewatch_api_key'

export const apiConfig = {
  getBaseUrl(): string {
    const custom = localStorage.getItem(STORAGE_API_URL_KEY)
    if (custom && custom.trim()) return custom.trim().replace(/\/+$/, '')
    return (import.meta.env.VITE_API_URL as string | undefined) ?? '/api'
  },
  setBaseUrl(url: string | null) {
    if (url) localStorage.setItem(STORAGE_API_URL_KEY, url)
    else localStorage.removeItem(STORAGE_API_URL_KEY)
  },
  getApiKey(): string {
    const custom = localStorage.getItem(STORAGE_API_KEY)
    if (custom && custom.trim()) return custom.trim()
    return (import.meta.env.VITE_API_KEY as string | undefined) ?? 'fortewatch-secret-key-2026'
  },
  setApiKey(key: string | null) {
    if (key) localStorage.setItem(STORAGE_API_KEY, key)
    else localStorage.removeItem(STORAGE_API_KEY)
  },
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Проверка доступности бэкенда на порте 8040
 */
export async function checkBackendHealth(): Promise<{ online: boolean; message: string; meta?: BackendMeta }> {
  const base = apiConfig.getBaseUrl()
  const apiKey = apiConfig.getApiKey()

  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 4000)

    // Пробуем /meta или /health
    let res = await fetch(`${base}/meta`, {
      headers: { 'X-API-Key': apiKey },
      signal: controller.signal,
    }).catch(() => null)

    if (!res || !res.ok) {
      res = await fetch(`${base}/health`, {
        headers: { 'X-API-Key': apiKey },
        signal: controller.signal,
      }).catch(() => null)
    }

    clearTimeout(timer)

    if (res && res.ok) {
      const data = await res.json().catch(() => ({}))
      return { online: true, message: 'Бэкенд доступен', meta: data }
    }

    return {
      online: false,
      message: res ? `Бэкенд вернул код ${res.status}` : 'Нет ответа от бэкенда (порт 8040)',
    }
  } catch (err: any) {
    return {
      online: false,
      message: err.name === 'AbortError' ? 'Таймаут соединения с бэкендом' : 'Бэкенд недоступен',
    }
  }
}

/**
 * Нормализация base64 изображения к data:image/jpeg;base64,...
 */
export function formatBase64Image(raw: string): string {
  if (!raw) return ''
  const trimmed = raw.trim()
  if (trimmed.startsWith('data:image')) return trimmed
  return `data:image/jpeg;base64,${trimmed}`
}

/**
 * Нормализатор ответов бэкенда под строгий контракт ТЗ
 */
export function normalizeAnalysisResponse(raw: any, jobId: string): AnalysisResponse {
  if (!raw || typeof raw !== 'object') {
    return {
      job_id: jobId,
      status: 'failed',
      error: 'Некорректный формат ответа от бэкенда',
      raw_response: raw,
    }
  }

  const status: JobStatus = (raw.status as JobStatus) || (raw.verdict ? 'done' : 'processing')

  // Сбор списка нарушений
  const rawList: any[] = Array.isArray(raw.violations)
    ? raw.violations
    : Array.isArray(raw.anomalies)
      ? raw.anomalies
      : []

  const violations: Violation[] = rawList.map((item: any) => {
    const typeStr = item.type || item.anomaly_type || item.violation_type || 'Обнаруженная аномалия'
    const timecode = Number(item.timecode_sec ?? item.timestamp_sec ?? 0)
    const desc = item.description || item.explanation || 'Визуально наблюдаемое отклонение от кассовой дисциплины'
    const ruleInfo = resolveRuleInfo(typeStr, item.rule || item.law_reference)

    // Обработка кадров-доказательств
    let evidenceFrames = []
    if (Array.isArray(item.evidence_frames) && item.evidence_frames.length > 0) {
      evidenceFrames = item.evidence_frames.map((f: any) => ({
        timestamp_sec: Number(f.timestamp_sec ?? timecode),
        image_base64: formatBase64Image(f.image_base64 || f.crop_base64 || ''),
      }))
    } else if (item.image_base64 || item.crop_base64 || item.evidence_crop) {
      evidenceFrames = [
        {
          timestamp_sec: timecode,
          image_base64: formatBase64Image(item.image_base64 || item.crop_base64 || item.evidence_crop),
        },
      ]
    }

    return {
      type: typeStr,
      timecode_sec: timecode,
      description: desc,
      rule: ruleInfo.fullCitation,
      normative_source: ruleInfo.document,
      confidence: typeof item.confidence === 'number' ? item.confidence : undefined,
      motion_score: typeof item.motion_score === 'number' ? item.motion_score : undefined,
      evidence_frames: evidenceFrames,
    }
  })

  // Определение итогового вердикта
  let verdict: 'violation' | 'no_violation' = 'no_violation'
  if (raw.verdict === 'violation' || raw.verdict === 'no_violation') {
    verdict = raw.verdict
  } else if (violations.length > 0 || raw.has_critical_anomaly) {
    verdict = 'violation'
  }

  return {
    job_id: raw.job_id || jobId,
    status: status,
    verdict: verdict,
    violations: violations,
    total_duration_sec: raw.total_duration_sec,
    processing_time_sec: raw.processing_time_sec,
    processed_segments_count: raw.processed_segments_count,
    video_path: raw.video_path,
    error: raw.error || raw.detail,
    raw_response: raw,
  }
}

/**
 * 1. Отправка видео на анализ (POST /api/v1/analyze)
 */
export async function uploadVideoForAnalysis(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ job_id: string; immediateResult?: AnalysisResponse }> {
  const base = apiConfig.getBaseUrl()
  const apiKey = apiConfig.getApiKey()

  const formData = new FormData()
  formData.append('file', file)

  // Пути для запроса с фоллбеком
  const endpointCandidates = [`${base}/v1/analyze`, `${base}/analyze`]

  let lastError: Error | null = null

  for (const endpoint of endpointCandidates) {
    try {
      const res = await new Promise<{ status: number; data: any }>((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('POST', endpoint)
        xhr.setRequestHeader('X-API-Key', apiKey)

        if (xhr.upload && onProgress) {
          xhr.upload.onprogress = (evt) => {
            if (evt.lengthComputable) {
              const pct = Math.round((evt.loaded / evt.total) * 100)
              onProgress(pct)
            }
          }
        }

        xhr.onload = () => {
          let parsed: any = null
          try {
            parsed = JSON.parse(xhr.responseText)
          } catch {
            parsed = xhr.responseText
          }
          resolve({ status: xhr.status, data: parsed })
        }

        xhr.onerror = () => reject(new ApiError(`Сетевая ошибка при обращении к ${endpoint}`, 0))
        xhr.ontimeout = () => reject(new ApiError(`Таймаут запроса к ${endpoint}`, 0))

        xhr.send(formData)
      })

      if (res.status === 404 && endpoint !== endpointCandidates[endpointCandidates.length - 1]) {
        continue // Пробуем следующий эндпоинт
      }

      if (res.status >= 200 && res.status < 300) {
        const data = res.data
        const jobId = data.job_id || `job_${Date.now()}`

        // Если бэкенд вернул результат синхронно
        if (data.status === 'done' || data.verdict) {
          return {
            job_id: jobId,
            immediateResult: normalizeAnalysisResponse(data, jobId),
          }
        }

        return { job_id: jobId }
      }

      const errMsg = typeof res.data?.detail === 'string'
        ? res.data.detail
        : `Ошибка сервера (${res.status}): ${JSON.stringify(res.data)}`
      throw new ApiError(errMsg, res.status, res.data)
    } catch (err: any) {
      lastError = err
      if (err instanceof ApiError && err.status !== 404 && err.status !== 0) {
        throw err
      }
    }
  }

  throw lastError || new ApiError('Не удалось отправить видео на бэкенд', 0)
}

/**
 * 2. Получение статуса задачи (GET /api/v1/jobs/{job_id})
 */
export async function fetchJobStatus(jobId: string): Promise<AnalysisResponse> {
  const base = apiConfig.getBaseUrl()
  const apiKey = apiConfig.getApiKey()

  const endpointCandidates = [
    `${base}/v1/jobs/${encodeURIComponent(jobId)}`,
    `${base}/jobs/${encodeURIComponent(jobId)}`,
  ]

  let lastError: Error | null = null

  for (const endpoint of endpointCandidates) {
    try {
      const res = await fetch(endpoint, {
        method: 'GET',
        headers: {
          'X-API-Key': apiKey,
          Accept: 'application/json',
        },
      })

      if (res.status === 404 && endpoint !== endpointCandidates[endpointCandidates.length - 1]) {
        continue
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        const msg = errData?.detail || `Бэкенд вернул ошибку ${res.status}`
        throw new ApiError(msg, res.status, errData)
      }

      const data = await res.json()
      return normalizeAnalysisResponse(data, jobId)
    } catch (err: any) {
      lastError = err
      if (err instanceof ApiError && err.status !== 404) {
        throw err
      }
    }
  }

  throw lastError || new ApiError(`Не удалось получить статус задачи ${jobId}`, 0)
}

/**
 * 3. Полный цикл опроса до завершения задачи (максимум 5 минут по регламенту ТЗ)
 */
export async function pollJobUntilComplete(
  jobId: string,
  onProgress?: (response: AnalysisResponse) => void,
  maxWaitSec = 300,
): Promise<AnalysisResponse> {
  const startTime = Date.now()
  const intervalMs = 1500

  while (true) {
    const elapsedSec = (Date.now() - startTime) / 1000

    if (elapsedSec > maxWaitSec) {
      throw new ApiError('Превышено время ожидания обработки (5 минут по регламенту ТЗ Datathon 26)', 408)
    }

    const result = await fetchJobStatus(jobId)

    if (onProgress) {
      onProgress(result)
    }

    if (result.status === 'done') {
      return result
    }

    if (result.status === 'failed') {
      throw new ApiError(result.error || 'Бэкенд завершил обработку со статусом failed', 500, result)
    }

    // Задержка перед следующим опросом
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}
