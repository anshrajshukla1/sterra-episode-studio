import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api'
import type { Job } from '../api'
import { ArrowUpRight } from '../components/icons'

interface LogLine {
  text: string
  type: 'info' | 'error' | 'warn' | 'done'
}

function classifyLog(line: string): LogLine['type'] {
  if (line.includes('[error]') || line.includes('ERROR')) return 'error'
  if (line.includes('WARNING') || line.includes('WARN')) return 'warn'
  if (line.includes('[done]') || line.includes('complete')) return 'done'
  return 'info'
}

export default function JobView() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [logs, setLogs] = useState<LogLine[]>([])
  const [progress, setProgress] = useState(0)
  const [done, setDone] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return

    // Load job info
    api.getJob(jobId).then(setJob).catch(() => {})

    // Connect SSE
    api.createJobStream(jobId).then(es => {
      esRef.current = es
      es.onmessage = (e) => {
        const text: string = e.data

        if (text === '__STREAM_DONE__') {
          setDone(true)
          es.close()
          // Reload job status
          api.getJob(jobId).then(setJob).catch(() => {})
          return
        }

        if (text.startsWith('__RESULT__:')) {
          return
        }

        setLogs(prev => [...prev, { text, type: classifyLog(text) }])

        // Parse progress from log lines
        const match = text.match(/(\d+)%/)
        if (match) setProgress(parseInt(match[1], 10))
        if (text.includes('Pipeline complete') || text.includes('[done]')) setProgress(100)
      }
      es.onerror = () => {
        setLogs(prev => [...prev, { text: 'Connection lost. Retrying...', type: 'warn' }])
      }
    })

    return () => {
      esRef.current?.close()
    }
  }, [jobId])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Auto-navigate to results when done
  useEffect(() => {
    if (done && job?.status === 'done') {
      setTimeout(() => navigate(`/app/results/${jobId}`), 1500)
    }
  }, [done, job])

  return (
    <div className="min-h-screen bg-black px-8 md:px-16 pt-28 pb-16">
      <div className="max-w-3xl">
        <p className="text-sm font-body text-white/50 mb-2">// Job Progress</p>
        <h1 className="font-heading italic text-4xl tracking-[-2px] leading-none text-white mb-2">
          Processing Recording
        </h1>
        <p className="text-xs font-body text-white/40 font-mono mb-8">{jobId}</p>

        {/* Progress bar */}
        <div className="liquid-glass rounded-full h-1.5 mb-8 overflow-hidden">
          <motion.div
            className="h-full bg-white rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ ease: 'easeOut' }}
          />
        </div>

        {/* Status badge */}
        <div className="flex items-center gap-3 mb-6">
          {!done && (
            <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
          )}
          {done && job?.status === 'done' && (
            <div className="w-2 h-2 rounded-full bg-green-400" />
          )}
          {done && job?.status === 'failed' && (
            <div className="w-2 h-2 rounded-full bg-red-400" />
          )}
          <span className="text-sm font-body text-white/70">
            {done
              ? job?.status === 'done' ? 'Complete — redirecting to results...' : `Failed: ${job?.error_msg}`
              : 'Running pipeline...'}
          </span>
        </div>

        {/* Terminal log */}
        <div className="liquid-glass rounded-2xl p-5 h-[420px] overflow-y-auto terminal-log">
          {logs.map((log, i) => (
            <div key={i} className={`log-${log.type} py-0.5 flex min-w-0`}>
              <span className="text-white/30 select-none mr-2 inline-block w-8 text-right shrink-0">{String(i + 1)} │</span>
              <span className="flex-1 truncate whitespace-nowrap" title={log.text}>{log.text}</span>
            </div>
          ))}
          {!done && (
            <div className="text-white/30 animate-pulse mt-1">▌</div>
          )}
          <div ref={logEndRef} />
        </div>

        {done && job?.status === 'done' && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6"
          >
            <button
              onClick={() => navigate(`/app/results/${jobId}`)}
              className="liquid-glass-strong rounded-full px-6 py-3 flex items-center gap-2 text-sm font-body font-medium text-white"
            >
              View Results
              <ArrowUpRight className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </div>
    </div>
  )
}
