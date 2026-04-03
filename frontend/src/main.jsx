import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './styles/index.css'

// Disable right-click in production to reduce info leakage
if (import.meta.env.PROD) {
  document.addEventListener('contextmenu', e => e.preventDefault())
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchOnWindowFocus: false,
      retry: (failCount, err) => {
        if (err?.response?.status === 401) return false
        return failCount < 2
      }
    }
  }
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
        <Toaster position="top-right" toastOptions={{
          style: { background:'#1e293b', color:'#f1f5f9', border:'1px solid #334155' },
          duration: 4000,
        }} />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
