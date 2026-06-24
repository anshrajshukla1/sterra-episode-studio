import { ArrowUpRight } from './icons'

const NAV_LINKS = ['Work', 'Studio', 'Services', 'Journal', 'Contact']

interface NavbarProps {
  onStartProject?: () => void
}

export default function Navbar({ onStartProject }: NavbarProps) {
  return (
    <nav className="fixed top-4 left-0 right-0 z-50 flex items-center justify-between px-8 lg:px-16">
      {/* Logo */}
      <div className="liquid-glass h-12 w-12 rounded-full flex items-center justify-center cursor-pointer">
        <span className="font-heading italic text-2xl text-white">a</span>
      </div>

      {/* Center nav links */}
      <div className="hidden md:flex">
        <div className="liquid-glass rounded-full px-1.5 py-1.5 flex items-center gap-1">
          <button
            onClick={onStartProject}
            className="ml-1 flex items-center gap-1.5 bg-white text-black rounded-full px-4 py-2 text-sm font-medium font-body hover:bg-white/90 transition-colors"
          >
            Enter Dashboard
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Spacer */}
      <div className="h-12 w-12" />
    </nav>
  )
}
