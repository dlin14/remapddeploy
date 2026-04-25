import Image from "next/image";
import USMap from "@/components/map/USMap";
import NationwideStatsPanel from "@/components/dashboard/NationwideStatsPanel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav bar */}
      <header className="flex items-center px-8 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt="remapd logo"
            width={36}
            height={36}
            className="rounded-lg"
            priority
          />
          <span className="font-bold text-base tracking-tight text-white/90">remapd</span>
        </div>
      </header>

      {/* Hero */}
      <section className="flex flex-col items-center justify-center pt-12 pb-6 px-8 text-center">
        <h1 className="text-6xl font-black tracking-tight leading-none bg-gradient-to-br from-white via-slate-200 to-slate-400 bg-clip-text text-transparent mb-5">
          remapd
        </h1>
        <p className="text-slate-400 text-base max-w-xl leading-relaxed">
          Congressional district boundaries determine whose voice gets heard — remapd uses{" "}
          <span className="text-indigo-400 font-medium">reinforcement learning agents</span> to
          autonomously redraw them, optimizing for racial fairness, population equality,
          compactness, and voting rights protections.
        </p>
      </section>

      {/* Map */}
      <section className="flex items-center justify-center px-8">
        <USMap />
      </section>

      {/* Nationwide improvement panel */}
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
