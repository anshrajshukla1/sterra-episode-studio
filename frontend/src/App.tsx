import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Hero from './pages/Hero'
import Login from './pages/Login'
import RecordingList from './pages/RecordingList'
import RecordingDetail from './pages/RecordingDetail'
import JobView from './pages/JobView'
import ResultView from './pages/ResultView'
import { isFirebaseConfigured } from './firebase'

export default function App() {
  if (!isFirebaseConfigured) {
    return (
      <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-8">
        <div className="max-w-2xl text-center space-y-6">
          <h1 className="text-4xl font-serif text-red-500">Configuration Required</h1>
          <p className="text-xl text-neutral-300">
            Firebase Authentication keys are missing. The application cannot start.
          </p>
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 text-left font-mono text-sm overflow-auto">
            <p className="text-yellow-500 mb-4">Please create a <code>.env</code> file in the project root with the following keys:</p>
            <pre className="text-neutral-400">
{`FIREBASE_PROJECT_ID="<your_project_id>"
VITE_FIREBASE_API_KEY="<your_api_key>"
VITE_FIREBASE_AUTH_DOMAIN="<your_auth_domain>"
VITE_FIREBASE_PROJECT_ID="<your_project_id>"
VITE_FIREBASE_STORAGE_BUCKET="<your_storage_bucket>"
VITE_FIREBASE_MESSAGING_SENDER_ID="<your_sender_id>"
VITE_FIREBASE_APP_ID="<your_app_id>"`}
            </pre>
          </div>
          <p className="text-neutral-400">After creating the file, restart Docker Compose.</p>
        </div>
      </div>
    )
  }

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
        <Route path="recordings/:recordingId" element={<RecordingDetail />} />
        <Route path="jobs/:jobId" element={<JobView />} />
        <Route path="results/:jobId" element={<ResultView />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
