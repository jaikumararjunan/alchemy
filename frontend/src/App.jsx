import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import DashboardPage   from '@/pages/DashboardPage'
import PortfolioPage   from '@/pages/PortfolioPage'
import SignalsPage     from '@/pages/SignalsPage'
import CryptoPage      from '@/pages/CryptoPage'
import RiskPage        from '@/pages/RiskPage'
import AnalyticsPage   from '@/pages/AnalyticsPage'
import StrategyPage    from '@/pages/StrategyPage'
import SettingsPage    from '@/pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"  element={<DashboardPage />} />
        <Route path="portfolio"  element={<PortfolioPage />} />
        <Route path="signals"    element={<SignalsPage />} />
        <Route path="crypto"     element={<CryptoPage />} />
        <Route path="risk"       element={<RiskPage />} />
        <Route path="analytics"  element={<AnalyticsPage />} />
        <Route path="strategy"   element={<StrategyPage />} />
        <Route path="settings"   element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
