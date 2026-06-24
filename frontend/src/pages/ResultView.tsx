import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api'
import type { Result } from '../api'
import { ArrowUpRight } from '../components/icons'
import { getIdToken } from '../firebase'

function HealthBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-white/40 font-body text-sm">N/A</span>
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'text-green-400' : pct >= 60 ? 'text-yellow-400' : 'text-red-400'
  return (
    <span className={`font-heading italic text-4xl tracking-[-1px] ${color}`}>
      {pct}<span className="text-xl">%</span>
    </span>
  )
}

export default function ResultView() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [result, setResult] = useState<Result | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [videoToken, setVideoToken] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return
    api.getResult(jobId)
      .then(r => { setResult(r); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
    getIdToken().then(setVideoToken)
  }, [jobId])

  if (loading) return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <div className="w-6 h-6 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
    </div>
  )

  if (error || !result) return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <p className="text-red-400 font-body">{error || 'Result not found'}</p>
    </div>
  )

  const meta = result.metadata_json
  const videoUrl = videoToken
    ? `${api.getVideoUrl(jobId!)}?token=${videoToken}`
    : api.getVideoUrl(jobId!)

  return (
    <div className="min-h-screen bg-black px-8 md:px-16 pt-28 pb-16">
      <div className="max-w-6xl">
        <div className="flex items-center gap-4 mb-8">
          <button
            onClick={() => navigate('/app')}
            className="liquid-glass rounded-full px-4 py-2 text-xs font-body text-white/60 hover:text-white transition-colors"
          >
            ← Back
          </button>
          <p className="text-sm font-body text-white/50">// Results</p>
        </div>

        <h1 className="font-heading italic text-5xl tracking-[-2px] leading-none text-white mb-8">
          Episode Results
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Video player - spans 2 cols */}
          <div className="lg:col-span-2">
            <div className="liquid-glass rounded-[1.25rem] overflow-hidden">
              <video
                src={videoUrl}
                controls
                className="w-full aspect-video bg-black"
                playsInline
              />
            </div>
          </div>

          {/* Metadata panel */}
          <div className="flex flex-col gap-4">
            {/* Health score */}
            <div className="liquid-glass rounded-[1.25rem] p-5">
              <p className="text-xs font-body text-white/50 mb-2">Health Score</p>
              <HealthBadge score={result.health_score} />
            </div>

            {/* Metadata */}
            <div className="liquid-glass rounded-[1.25rem] p-5 flex-1">
              <p className="text-xs font-body text-white/50 mb-4">Recording Metadata</p>
              <div className="space-y-3">
                {[
                  { label: 'Duration', value: meta.duration_s ? `${Math.floor(meta.duration_s / 60)}m ${Math.floor(meta.duration_s % 60)}s` : '—' },
                  { label: 'Frames', value: meta.frame_count?.toLocaleString() || '—' },
                  { label: 'Depth', value: meta.has_depth ? '✓ Present' : '✗ Missing' },
                  { label: 'Pose', value: meta.has_pose ? '✓ Present' : '✗ Missing' },
                ].map(item => (
                  <div key={item.label} className="flex justify-between">
                    <span className="text-xs font-body text-white/50">{item.label}</span>
                    <span className="text-xs font-body text-white">{item.value}</span>
                  </div>
                ))}
                <div>
                  <p className="text-xs font-body text-white/50 mb-1">Streams</p>
                  <div className="flex flex-wrap gap-1">
                    {(meta.stream_names || []).map(s => (
                      <span key={s} className="liquid-glass rounded-full px-2 py-0.5 text-[10px] font-body text-white/70">{s}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* QC Report */}
        {result.report_path && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-6"
          >
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-heading italic text-2xl tracking-[-1px] text-white">QC Report</h2>
              <a
                href={`${api.getReportUrl(jobId!)}?token=${videoToken}`}
                target="_blank"
                rel="noopener noreferrer"
                className="liquid-glass rounded-full px-3 py-1.5 text-xs font-body text-white/70 flex items-center gap-1.5 hover:text-white transition-colors"
              >
                Open in new tab <ArrowUpRight className="w-3 h-3" />
              </a>
            </div>
            <div className="liquid-glass rounded-[1.25rem] overflow-hidden">
              <iframe
                src={`${api.getReportUrl(jobId!)}?token=${videoToken}`}
                className="w-full h-[500px] border-0"
                title="QC Report"
              />
            </div>
          </motion.div>
        )}
      </div>
    </div>
  )
}
