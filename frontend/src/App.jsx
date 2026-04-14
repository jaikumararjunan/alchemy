import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import { ProtectedRoute, PublicRoute } from '@/components/auth/ProtectedRoute'
import Layout from '@/components/layout/Layout'

// Auth pages
import LoginPage        from '@/pages/auth/LoginPage'
import SignupPage       from '@/pages/auth/SignupPage'
import ForgotPasswordPage from '@/pages/auth/ForgotPasswordPage'
import ResetPasswordPage  from '@/pages/auth/ResetPasswordPage'
import TwoFASetupPage   from '@/pages/auth/TwoFASetupPage'

// App pages
import DashboardPage      from '@/pages/DashboardPage'
import PortfolioPage      from '@/pages/PortfolioPage'
import SignalsPage        from '@/pages/SignalsPage'
import CryptoPage         from '@/pages/CryptoPage'
import RiskPage           from '@/pages/RiskPage'
import AnalyticsPage      from '@/pages/AnalyticsPage'
import StrategyPage       from '@/pages/StrategyPage'
import AutonomousTradingPage from '@/pages/AutonomousTradingPage'
import PaperTradingPage from '@/pages/PaperTradingPage'
import TokenManagerPage   from '@/pages/TokenManagerPage'
import WorkflowPage       from '@/pages/WorkflowPage'
import NotificationsPage  from '@/pages/NotificationsPage'
import SettingsPage       from '@/pages/SettingsPage'
import SecurityDashboardPage from '@/pages/SecurityDashboardPage'

// Admin pages
import AdminDashboard from '@/pages/admin/AdminDashboard'
import SubscriptionPage from '@/pages/SubscriptionPage'
import WatchlistPage from '@/pages/WatchlistPage'
import AlertsPage from '@/pages/AlertsPage'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Public auth routes */}
        <Route path="/auth/login"     element={<PublicRoute><LoginPage /></PublicRoute>} />
        <Route path="/auth/forgot-password" element={<PublicRoute><ForgotPasswordPage /></PublicRoute>} />
        <Route path="/auth/reset-password"  element={<PublicRoute><ResetPasswordPage /></PublicRoute>} />
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
          <Route path="autonomous"    element={<AutonomousTradingPage />} />
          <Route path="paper-trading" element={<PaperTradingPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="settings"      element={<SettingsPage />} />
          <Route path="watchlist"     element={<WatchlistPage />} />
          <Route path="alerts"        element={<AlertsPage />} />

          {/* Admin-only */}
          <Route path="subscription" element={<SubscriptionPage />} />
          <Route path="admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  )
}
