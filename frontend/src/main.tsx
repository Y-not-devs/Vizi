import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './App'
import { MetaProvider } from './context/MetaContext'
import { AuthProvider } from './features/auth/AuthContext'
import { ToastProvider } from './components/ui'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MetaProvider>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </MetaProvider>
  </React.StrictMode>
)
