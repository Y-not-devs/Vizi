/**
 * Утилиты форматирования для ForteWatch
 */

export function formatTimecode(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  const ms = Math.floor((seconds % 1) * 10)

  const minStr = mins.toString().padStart(2, '0')
  const secStr = secs.toString().padStart(2, '0')

  return `${minStr}:${secStr}.${ms}`
}

export function formatSecondsShort(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '0 сек'
  return `${seconds.toFixed(1)} сек`
}

export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes === 0) return '0 Б'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}
