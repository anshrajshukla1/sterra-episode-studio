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
          {/* Badge */}
          <motion.div
            variants={fadeVariant}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            <div className="liquid-glass rounded-full px-4 py-2 inline-flex items-center gap-2">
              <span className="bg-white text-black text-xs font-semibold font-body px-2 py-0.5 rounded-full">New</span>
              <span className="text-sm text-white/80 font-body">Booking Q3 2026 engagements — limited capacity</span>
            </div>
          </motion.div>

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

          {/* Stats cards */}
          <motion.div
            variants={fadeVariant}
            initial="hidden"
            animate="visible"
            transition={{ duration: 0.8, delay: 1.3 }}
            className="mt-8 flex gap-4 flex-wrap justify-center"
          >
            {[{
              icon: <ClockIcon className="w-5 h-5 text-white/60" />,
              value: '6 Weeks',
              label: 'Average End-to-End Launch Time',
            }, {
              icon: <GlobeIcon className="w-5 h-5 text-white/60" />,
              value: '140+',
              label: 'Brands Shipped Across Four Continents',
            }].map(card => (
              <div key={card.value} className="liquid-glass p-5 w-[220px] rounded-[1.25rem] text-left">
                {card.icon}
                <p className="text-4xl font-heading italic tracking-[-1px] leading-none mt-4">{card.value}</p>
                <p className="text-xs text-white/60 font-body mt-2 leading-tight">{card.label}</p>
              </div>
            ))}
          </motion.div>
        </div>

        {/* Trust bar */}
        <motion.div
          variants={fadeVariant}
          initial="hidden"
          animate="visible"
          transition={{ duration: 0.8, delay: 1.4 }}
          className="flex flex-col items-center gap-4 pb-8"
        >
          <div className="liquid-glass rounded-full px-4 py-2">
            <span className="text-xs text-white/70 font-body">Trusted by founders, operators, and creative directors worldwide</span>
          </div>
          <div className="flex items-center gap-12 md:gap-16">
            {LOGOS.map(logo => (
              <span key={logo} className="font-heading italic text-2xl md:text-3xl tracking-tight text-white/80">{logo}</span>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
