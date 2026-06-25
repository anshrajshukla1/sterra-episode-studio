import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Recording } from '../api'
import { ArrowUpRight } from '../components/icons'

export default function RecordingDetail() {
  const { recordingId } = useParams<{ recordingId: string }>()
  const navigate = useNavigate()
  const [recording, setRecording] = useState<Recording | null>(null)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!recordingId) return
    api.getRecording(recordingId).then(setRecording).catch(e => setError(e.message))
  }, [recordingId])

  const handleProcess = async () => {
    if (!recordingId) return
    setProcessing(true)
    setError(null)
    try {
      const job = await api.createJob(recordingId)
      navigate(`/app/jobs/${job.id}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start processing')
      setProcessing(false)
    }
  }

  if (!recording) return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      {error ? (
        <p className="text-red-400 font-body">{error}</p>
      ) : (
        <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
      )}
    </div>
  )

  return (
    <div className="min-h-screen bg-black px-8 md:px-16 pt-28 pb-16">
      <div className="max-w-2xl">
        <button
          onClick={() => navigate('/app')}
          className="liquid-glass rounded-full px-4 py-2 text-xs font-body text-white/60 hover:text-white transition-colors mb-8"
        >
          ← Back
        </button>

        <p className="text-sm font-body text-white/50 mb-2">// Recording</p>
        <h1 className="font-heading italic text-4xl md:text-5xl tracking-[-2px] leading-none text-white mb-2">
          {recording.filename}
        </h1>

        <div className="liquid-glass rounded-[1.25rem] p-6 mt-8 space-y-4">
          {[
            { label: 'File size', value: `${(recording.size_bytes / 1024 / 1024).toFixed(1)} MB` },
            { label: 'Status', value: recording.status },
            { label: 'Duration', value: recording.duration_s ? `${Math.floor(recording.duration_s / 60)}m ${Math.floor(recording.duration_s % 60)}s` : 'Not yet processed' },
            { label: 'Streams', value: recording.stream_names?.join(', ') || 'Not yet scanned' },
          ].map(item => (
            <div key={item.label} className="flex justify-between border-b border-white/5 pb-4 last:border-0 last:pb-0">
              <span className="text-sm font-body text-white/50">{item.label}</span>
              <span className="text-sm font-body text-white">{item.value}</span>
            </div>
          ))}
        </div>

        {error && (
          <p className="mt-4 text-red-400 font-body text-sm">{error}</p>
        )}

        <div className="mt-8 flex flex-wrap gap-4">
          {recording.status === 'done' ? (
            <>
              <button
                onClick={() => navigate(recording.latest_job_id ? `/app/results/${recording.latest_job_id}` : '/app')}
                className="liquid-glass-strong rounded-full px-6 py-3 flex items-center gap-2 text-sm font-body font-medium text-white"
              >
                View Results <ArrowUpRight className="w-4 h-4" />
              </button>
              <button
                onClick={handleProcess}
                disabled={processing}
                className="liquid-glass rounded-full px-6 py-3 flex items-center gap-2 text-sm font-body font-medium text-white hover:bg-white/5 transition-colors disabled:opacity-50"
              >
                {processing ? (
                  <>
                    <div className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
                    Starting...
                  </>
                ) : 'Re-run Pipeline'}
              </button>
            </>
          ) : recording.status === 'processing' ? (
            <>
              {recording.latest_job_id && (
                <button
                  onClick={() => navigate(`/app/jobs/${recording.latest_job_id}`)}
                  className="liquid-glass-strong rounded-full px-6 py-3 flex items-center gap-2 text-sm font-body font-medium text-white"
                >
                  View Job Progress <ArrowUpRight className="w-4 h-4" />
                </button>
              )}
              <button
                disabled
                className="liquid-glass rounded-full px-6 py-3 text-sm font-body font-medium text-white/40 cursor-not-allowed"
              >
                Processing...
              </button>
            </>
          ) : (
            <button
              onClick={handleProcess}
              disabled={processing}
              className="liquid-glass-strong rounded-full px-6 py-3 flex items-center gap-2 text-sm font-body font-medium text-white disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {processing ? (
                <>
                  <div className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
                  Starting...
                </>
              ) : recording.status === 'error' ? 'Retry Processing' : 'Process Recording'}
              {!processing && <ArrowUpRight className="w-4 h-4" />}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
