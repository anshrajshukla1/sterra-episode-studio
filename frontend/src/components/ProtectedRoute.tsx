import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
      </div>
    )
  }

  if (!user && import.meta.env.VITE_FIREBASE_API_KEY !== 'dummy') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
