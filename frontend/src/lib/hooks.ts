import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Загрузка данных с состоянием loading/error и refetch.
 *
 *   const { data, loading, error, refetch } = useQuery(() => itemsApi.list({ q }), [q])
 */
export function useQuery<T>(fn: () => Promise<T>, deps: unknown[] = [], { enabled = true } = {}) {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [version, setVersion] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fnRef
      .current()
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((err: Error) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version, enabled])

  const refetch = useCallback(() => setVersion((v) => v + 1), [])
  return { data, setData, error, loading, refetch }
}

/**
 * Действие (POST/PATCH/DELETE) с состоянием loading/error.
 *
 *   const create = useMutation(itemsApi.create)
 *   await create.mutate({ title: 'New' })
 */
export function useMutation<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const mutate = useCallback(async (...args: A): Promise<R> => {
    setLoading(true)
    setError(null)
    try {
      return await fnRef.current(...args)
    } catch (err) {
      setError(err as Error)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { mutate, loading, error }
}

/** Значение с задержкой — для поиска по мере ввода. */
export function useDebounced<T>(value: T, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}
