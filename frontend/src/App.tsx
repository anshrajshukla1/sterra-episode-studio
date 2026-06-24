import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Hero from './pages/Hero'
import Capabilities from './pages/Capabilities'
import Login from './pages/Login'
import RecordingList from './pages/RecordingList'
import RecordingDetail from './pages/RecordingDetail'
import JobView from './pages/JobView'
import ResultView from './pages/ResultView'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={
        <div className="bg-black text-white min-h-screen">
          <Hero />
        </div>
      } />
      <Route path="/login" element={<Login />} />

      <Route path="/app" element={<ProtectedRoute />}>
        <Route index element={<RecordingList />} />
        <Route path="recordings/:id" element={<RecordingDetail />} />
        <Route path="jobs/:id" element={<JobView />} />
        <Route path="results/:id" element={<ResultView />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
