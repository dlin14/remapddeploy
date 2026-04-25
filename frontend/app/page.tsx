import USMap from "@/components/map/USMap";
import NationwideStatsPanel from "@/components/dashboard/NationwideStatsPanel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav bar */}
      <header className="flex items-center justify-between px-8 py-4 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-[10px] font-black tracking-tight">
            R
          </div>
          <span className="font-semibold text-sm tracking-wide text-white/90">remapd</span>
        </div>
        <nav className="flex items-center gap-6 text-xs text-white/50">
          <span>Hackathon 2025</span>
          <span className="px-2 py-0.5 rounded-full border border-indigo-500/40 text-indigo-400 bg-indigo-500/10">
            v0.1 alpha
          </span>
        </nav>
      </header>

      {/* Hero */}
      <section className="flex flex-col items-center justify-center pt-14 pb-8 px-8 text-center">
        <h1 className="text-6xl font-black tracking-tight leading-none bg-gradient-to-br from-white via-slate-200 to-slate-400 bg-clip-text text-transparent mb-4">
          remapd
        </h1>
        <p className="text-slate-400 text-base max-w-md leading-relaxed">
          Simulated-annealing redistricting optimizer. Click any state to tune
          parameters, run the optimizer, and see fair district maps emerge in real time.
        </p>
      </section>

      {/* Map */}
      <section className="flex items-center justify-center px-8">
        <USMap />
      </section>

      {/* Nationwide improvement panel (only shown after first optimizer run) */}
      <section className="px-8 pb-8">
        <NationwideStatsPanel />
      </section>

      {/* Footer stats strip */}
      <footer className="border-t border-white/10 px-8 py-5 flex items-center justify-between gap-6 flex-wrap mt-auto">
        <div className="flex items-center gap-8">
          <Stat label="Optimizer" value="Simulated Annealing" />
          <Stat label="Objective" value="Racial · Pop · Compact · VRA" />
          <Stat label="Data" value="ACS 5-yr County FIPS" />
        </div>
        <p className="text-[11px] text-white/25 font-mono">
          built for claude hackathon 2025 · anthropic
        </p>
      </footer>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] text-white/35 uppercase tracking-widest font-medium mb-0.5">{label}</p>
      <p className="text-xs text-white/70 font-mono">{value}</p>
    </div>
  );
}
