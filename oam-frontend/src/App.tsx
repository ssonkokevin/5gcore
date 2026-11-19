import { Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { Dashboard } from './pages/Dashboard'
import { Subscribers } from './pages/subscribers/Subscribers'
import { SubscriberDetail } from './pages/subscribers/SubscriberDetail'
import { BatchUpload } from './pages/subscribers/BatchUpload'
import { IMSIRanges } from './pages/subscribers/IMSIRanges'
import { AuthVectors } from './pages/subscribers/AuthVectors'
import { DRAManagement } from './pages/dra/DRAManagement'
import { STPManagement } from './pages/stp/STPManagement'
import { NetworkNodes } from './pages/network/NetworkNodes'
import { ReferenceData } from './pages/reference/ReferenceData'
import { USSDManagement } from './pages/ussd/USSDManagement'
import { KPISettings } from './pages/settings/KPISettings'
import { Login } from './pages/auth/Login'
import { useAuth } from './context/AuthContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'

function AppRoutes() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route
        element={
          <ProtectedRoute>
            <div className="flex h-screen bg-surface-50 dark:bg-surface-900">
              <Sidebar />
              <div className="flex-1 flex flex-col overflow-hidden">
                <Header />
                <main className="flex-1 overflow-auto p-6">
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/subscribers" element={<Subscribers />} />
                    <Route path="/subscribers/:imsi" element={<SubscriberDetail />} />
                    <Route path="/batch-upload" element={<BatchUpload />} />
                    <Route path="/imsi-ranges" element={<IMSIRanges />} />
                    <Route path="/auth-vectors" element={<AuthVectors />} />
                    <Route path="/dra" element={<DRAManagement />} />
                    <Route path="/stp" element={<STPManagement />} />
                    <Route path="/network-nodes" element={<NetworkNodes />} />
                    <Route path="/reference" element={<ReferenceData />} />
                    <Route path="/ussd" element={<USSDManagement />} />
                    <Route path="/settings/kpi" element={<KPISettings />} />
                  </Routes>
                </main>
              </div>
            </div>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AppRoutes />
  )
}