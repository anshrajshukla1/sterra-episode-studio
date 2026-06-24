import { useRef, useEffect } from 'react'

interface FadingVideoProps {
  src: string | string[]
  className?: string
  style?: React.CSSProperties
}

export default function FadingVideo({ src, className = '', style }: FadingVideoProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const indexRef = useRef(0)
  const sources = Array.isArray(src) ? src : [src]

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.style.opacity = '0'

    const fadeIn = () => {
      let start: number | null = null
      const duration = 500
      const step = (timestamp: number) => {
        if (!start) start = timestamp
        const progress = Math.min((timestamp - start) / duration, 1)
        video.style.opacity = String(progress)
        if (progress < 1) requestAnimationFrame(step)
      }
      requestAnimationFrame(step)
    }

    const fadeOut = (onDone?: () => void) => {
      let start: number | null = null
      const duration = 550
      const currentOpacity = parseFloat(video.style.opacity || '1')
      const step = (timestamp: number) => {
        if (!start) start = timestamp
        const progress = Math.min((timestamp - start) / duration, 1)
        video.style.opacity = String(currentOpacity * (1 - progress))
        if (progress < 1) {
          requestAnimationFrame(step)
        } else if (onDone) {
          onDone()
        }
      }
      requestAnimationFrame(step)
    }

    const handleLoaded = () => fadeIn()

    const handleTimeUpdate = () => {
      const remaining = video.duration - video.currentTime
      if (remaining <= 0.55 && parseFloat(video.style.opacity || '1') > 0.01) {
        // Only trigger once per cycle
        video.style.opacity = '0.009' // sentinel
        fadeOut()
      }
    }

    const handleEnded = () => {
      if (sources.length === 1) {
        video.currentTime = 0
        video.play().catch(() => {})
        video.style.opacity = '0'
        fadeIn()
      } else {
        indexRef.current = (indexRef.current + 1) % sources.length
        video.src = sources[indexRef.current]
        video.load()
        video.play().catch(() => {})
      }
    }

    video.addEventListener('loadeddata', handleLoaded)
    video.addEventListener('timeupdate', handleTimeUpdate)
    video.addEventListener('ended', handleEnded)

    return () => {
      video.removeEventListener('loadeddata', handleLoaded)
      video.removeEventListener('timeupdate', handleTimeUpdate)
      video.removeEventListener('ended', handleEnded)
    }
  }, [])

  return (
    <video
      ref={videoRef}
      src={sources[0]}
      className={className}
      style={{ opacity: 0, ...style }}
      autoPlay
      muted
      playsInline
      preload="auto"
    />
  )
}
