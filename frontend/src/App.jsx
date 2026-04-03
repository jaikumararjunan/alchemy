import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ProtectedRoute, PublicRoute } from '@/components/auth/ProtectedRoute'
import Layout from '@/components/layout/Layout'

// Auth pages
import LoginPage        from '@/pages/auth/LoginPage'
import SignupPage       from '@/pages/auth/SignupPage'
import TwoFASetupPage   from '@/pages/auth/TwoFASetupPage'

// App pages
import DashboardPage      from '@/pages/DashboardPage'
import PortfolioPage      from '@/pages/PortfolioPage'
import SignalsPage        from '@/pages/SignalsPage'
import CryptoPage         from '@/pages/CryptoPage'
import RiskPage           from '@/pages/RiskPage'
import AnalyticsPage      from '@/pages/AnalyticsPage'
import StrategyPage       from '@/pages/StrategyPage'
import TokenManagerPage   from '@/pages/TokenManagerPage'
import WorkflowPage       from '@/pages/WorkflowPage'
import NotificationsPage  from '@/pages/NotificationsPage'
import SettingsPage       from '@/pages/SettingsPage'

// Admin pages
import AdminDashboard from '@/pages/admin/AdminDashboard'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public auth routes */}
        <Route path="/auth/login"     element={<PublicRoute><LoginPage /></PublicRoute>} />
        <Route path="/auth/signup"    element={<PublicRoute><SignupPage /></PublicRoute>} />
        <Route path="/auth/2fa/setup" element={<ProtectedRoute><TwoFASetupPage /></ProtectedRoute>} />

        {/* Protected app routes */}
        <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard"     element={<DashboardPage />} />
          <Route path="portfolio"     element={<PortfolioPage />} />
          <Route path="signals"       element={<SignalsPage />} />
          <Route path="crypto"        element={<CryptoPage />} />
          <Route path="tokens"        element={<TokenManagerPage />} />
          <Route path="workflows"     element={<WorkflowPage />} />
          <Route path="risk"          element={<RiskPage />} />
          <Route path="analytics"     element={<AnalyticsPage />} />
          <Route path="strategy"      element={<StrategyPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="settings"      element={<SettingsPage />} />

          {/* Admin-only */}
          <Route path="admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}
