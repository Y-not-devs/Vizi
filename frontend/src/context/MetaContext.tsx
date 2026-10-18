import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '@/lib/api'
import type { AppMeta } from '@/types'

interface MetaContextType {
  meta: AppMeta | null
  healthy: boolean | null
  loading: boolean
  refetch: () => void
}

const MetaContext = createContext<MetaContextType>({
  meta: null,
  healthy: null,
  loading: true,
  refetch: () => {},
})

export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<AppMeta | null>(null)
  const [healthy, setHealthy] = useState<boolean | null>(null)
  const [loading, setLoading] = useState(true)

  const check = async () => {
    try {
      const [m, h] = await Promise.all([
        api.get<AppMeta>('/meta'),
        api.get<{ status: string }>('/health').catch(() => null),
      ])
      setMeta(m)
      setHealthy(h?.status === 'ok')
    } catch {
      setHealthy(false)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    check()
  }, [])

  return (
    <MetaContext.Provider value={{ meta, healthy, loading, refetch: check }}>
      {children}
    </MetaContext.Provider>
  )
}

export const useAppMeta = () => useContext(MetaContext)
