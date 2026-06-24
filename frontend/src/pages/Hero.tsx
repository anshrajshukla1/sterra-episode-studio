import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import FadingVideo from '../components/FadingVideo'
import BlurText from '../components/BlurText'
import Navbar from '../components/Navbar'
import { ArrowUpRight, Play, ClockIcon, GlobeIcon } from '../components/icons'

const fadeVariant = {
  hidden: { filter: 'blur(10px)', opacity: 0, y: 20 },
  visible: { filter: 'blur(0px)', opacity: 1, y: 0 },
}

const HERO_VIDEO = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260619_191346_9d19d66e-86a4-47f7-8dc6-712c1788c3b2.mp4'

const LOGOS = ['Aeon', 'Vela', 'Apex', 'Orbit', 'Zeno']

export default function Hero() {
  const navigate = useNavigate()
  return (
    <section className="h-screen overflow-hidden bg-black relative">
      {/* Background video */}
      <FadingVideo
        src={HERO_VIDEO}
        className="absolute left-1/2 top-0 -translate-x-1/2 object-cover object-top z-0"
        style={{ width: '120%', height: '120%' }}
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col h-full">
        <Navbar onStartProject={() => navigate('/app')} />

        {/* Main content */}
        <div className="flex-1 flex flex-col items-center justify-center pt-24 px-4 text-center">
          {/* Headline */}
          <div className="mt-6 max-w-3xl">
            <BlurText
              text="Episode Studio Processing Pipeline"
              className="text-6xl md:text-7xl lg:text-[5.5rem] font-heading italic text-white leading-[0.8] tracking-[-4px]"
            />
          </div>

          {/* Subtext */}
          <motion.p
            variants={fadeVariant}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.8, delay: 0.8 }}
            className="mt-4 text-sm md:text-base text-white max-w-2xl font-body font-light leading-tight"
          >
            Internal tool for batch processing, PII redaction, and QC evaluation of MCAP robotic datasets.
          </motion.p>

          {/* CTA buttons */}
          <motion.div
            variants={fadeVariant}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.8, delay: 1.1 }}
            className="mt-6 flex items-center justify-center"
          >
            <button
              onClick={() => navigate('/app')}
              className="liquid-glass-strong rounded-full px-5 py-2.5 flex items-center gap-2 text-sm font-body font-medium text-white hover:bg-white/10 transition-colors"
            >
              Enter Dashboard
              <ArrowUpRight className="w-4 h-4" />
            </button>
          </motion.div>

        </div>
      </div>
    </section>
  )
}
