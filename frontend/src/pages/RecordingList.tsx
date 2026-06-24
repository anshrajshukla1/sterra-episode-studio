import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api'
import type { Recording } from '../api'
import { FileIcon, RefreshIcon, ChevronRightIcon } from '../components/icons'

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function formatDuration(s: number | null): string {
  if (!s) return '—'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}m ${sec}s`
}

const STATUS_COLORS: Record<string, string> = {
  unprocessed: 'text-white/50 bg-white/5',
  processing: 'text-yellow-300 bg-yellow-300/10',
  done: 'text-green-400 bg-green-400/10',
  error: 'text-red-400 bg-red-400/10',
}

export default function RecordingList() {
  const [recordings, setRecordings] = useState<Recording[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getRecordings()
      setRecordings(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="min-h-screen bg-black px-8 md:px-16 pt-28 pb-16">
      {/* Header */}
      <div className="flex items-end justify-between mb-10">
        <div>
          <p className="text-sm font-body text-white/50 mb-2">// Recordings</p>
          <h1 className="font-heading italic text-5xl md:text-6xl tracking-[-2px] leading-none text-white">
            Episode Studio
          </h1>
          <p className="mt-3 text-sm font-body text-white/60 max-w-lg">
            MCAP recordings scanned from <code className="text-white/80 bg-white/5 px-1.5 py-0.5 rounded text-xs">RECORDINGS_DIR</code>.
            Select one to process through the Stera pipeline.
          </p>
        </div>
        <button
          onClick={load}
          className="liquid-glass rounded-full p-3 hover:bg-white/5 transition-colors"
          title="Refresh"
        >
          <RefreshIcon className="w-5 h-5 text-white/70" />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-3 text-white/50 font-body text-sm">
          <div className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
          Scanning recordings directory...
        </div>
      )}

      {error && (
        <div className="liquid-glass rounded-2xl p-4 border-red-500/20 text-red-400 font-body text-sm">
          ⚠ {error}
        </div>
      )}

      {!loading && !error && recordings.length === 0 && (
        <div className="text-center py-24">
          <p className="font-heading italic text-3xl text-white/30">No recordings found</p>
          <p className="mt-2 text-sm font-body text-white/30">
            Add .mcap files to your RECORDINGS_DIR and refresh.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        {recordings.map((rec, i) => (
          <motion.div
            key={rec.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05, duration: 0.4 }}
          >
            <div
              className="liquid-glass rounded-[1.25rem] p-5 flex flex-col gap-4 group hover:bg-white/[0.03] transition-colors cursor-pointer h-full"
              onClick={() => navigate(`/app/recordings/${rec.id}`)}
            >
              {/* Top */}
              <div className="flex items-start justify-between">
                <div className="liquid-glass h-10 w-10 rounded-[0.75rem] flex items-center justify-center flex-shrink-0">
                  <FileIcon className="w-4 h-4 text-white/70" />
                </div>
                <span className={`text-xs font-body px-2.5 py-1 rounded-full ${STATUS_COLORS[rec.status]}`}>
                  {rec.status}
                </span>
              </div>

              {/* Name */}
              <div className="flex-1">
                <p className="font-body font-medium text-white text-sm leading-snug break-all">{rec.filename}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-body text-white/50">
                  <span>{formatBytes(rec.size_bytes)}</span>
                  {rec.duration_s && <span>{formatDuration(rec.duration_s)}</span>}
                  {rec.stream_names && (
                    <span>{rec.stream_names.join(', ')}</span>
                  )}
                </div>
              </div>

              {/* Action */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-body text-white/30">
                  {new Date(rec.created_at).toLocaleDateString()}
                </span>
                <div className="liquid-glass-strong rounded-full px-3 py-1.5 flex items-center gap-1.5 text-xs font-body text-white opacity-0 group-hover:opacity-100 transition-opacity">
                  {rec.status === 'done' ? 'View Results' : 'Process'}
                  <ChevronRightIcon className="w-3 h-3" />
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
