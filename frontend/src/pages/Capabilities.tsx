import FadingVideo from '../components/FadingVideo'
import BlurText from '../components/BlurText'
import { ImageIcon, MovieIcon, LightbulbIcon } from '../components/icons'

const CAPABILITIES_VIDEO = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260622_093722_ccfc7ebf-182f-419f-8a62-2dc02db7dd9d.mp4'

const CARDS = [
  {
    icon: <ImageIcon className="w-5 h-5 text-white" />,
    title: 'Design',
    tags: ['Brand Systems', 'Art Direction', 'Visual Identity', 'Motion'],
    body: 'We shape identities and interfaces that feel unmistakably yours — typographic systems, component libraries, and art-directed pages that scale without losing soul.',
  },
  {
    icon: <MovieIcon className="w-5 h-5 text-white" />,
    title: 'Engineering',
    tags: ['React', 'Next.js', 'Headless CMS', 'Edge-Ready'],
    body: 'Production-grade front-ends built on modern stacks. Performant, accessible, and instrumented — with code your team will enjoy extending long after launch.',
  },
  {
    icon: <LightbulbIcon className="w-5 h-5 text-white" />,
    title: 'Growth',
    tags: ['SEO', 'Analytics', 'A/B Testing', 'Retention'],
    body: 'Launch is the starting line. We partner with your team on conversion, content, and iteration loops that turn a beautiful site into a compounding asset.',
  },
]

export default function Capabilities() {
  return (
    <section className="min-h-screen overflow-hidden bg-black relative">
      <FadingVideo
        src={CAPABILITIES_VIDEO}
        className="absolute inset-0 w-full h-full object-cover z-0"
      />

      <div className="relative z-10 px-8 md:px-16 lg:px-20 pt-24 pb-10 flex flex-col min-h-screen">
        {/* Header */}
        <div className="mb-auto">
          <p className="text-sm font-body text-white/80 mb-6">// Capabilities</p>
          <BlurText
            text="Studio craft, end to end"
            className="font-heading italic text-6xl md:text-7xl lg:text-[6rem] leading-[0.9] tracking-[-3px] text-white"
          />
        </div>

        {/* Cards */}
        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
          {CARDS.map(card => (
            <div key={card.title} className="liquid-glass rounded-[1.25rem] p-6 min-h-[360px] flex flex-col">
              {/* Top row: icon + tags */}
              <div className="flex items-start justify-between gap-3">
                <div className="liquid-glass h-11 w-11 rounded-[0.75rem] flex items-center justify-center flex-shrink-0">
                  {card.icon}
                </div>
                <div className="flex flex-wrap gap-1.5 justify-end">
                  {card.tags.map(tag => (
                    <span key={tag} className="liquid-glass rounded-full px-3 py-1 text-[11px] text-white/90 font-body whitespace-nowrap">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex-1" />

              {/* Bottom: title + body */}
              <div>
                <h3 className="font-heading italic text-3xl md:text-4xl tracking-[-1px] leading-none text-white">{card.title}</h3>
                <p className="mt-2 text-sm text-white/90 font-body font-light leading-snug max-w-[32ch]">{card.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
