import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, tokenStore } from '@/lib/api'
import type { TokenResponse, User } from '@/types'

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (tokenData: TokenResponse) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = tokenStore.get()
    if (!token) {
      setLoading(false)
      return
    }

    api
      .get<User>('/auth/me')
      .then(setUser)
      .catch(() => {
        tokenStore.set(null)
        setUser(null)
      })
      .finally(() => setLoading(false))

    const handleLogout = () => setUser(null)
    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [])

  const login = (tokenData: TokenResponse) => {
    tokenStore.set(tokenData.access_token)
    setUser(tokenData.user)
  }

  const logout = () => {
    tokenStore.set(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
