import Image from "next/image";
import USMap from "@/components/map/USMap";
import NationwideStatsPanel from "@/components/dashboard/NationwideStatsPanel";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col">
      {/* Top nav bar */}
      <header className="flex items-center px-8 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl overflow-hidden shrink-0">
            <Image
              src="/logo.png"
              alt="remapd logo"
              width={120}
              height={48}
              className="h-full w-auto max-w-none"
              style={{ objectFit: "cover", objectPosition: "left center" }}
              priority
            />
          </div>
          <span className="font-bold text-base tracking-tight text-white/90">remapd</span>
        </div>
      </header>

      {/* Hero */}
      <section className="flex flex-col items-center justify-center pt-12 pb-6 px-8 text-center">
        <h1 className="text-6xl font-black tracking-tight leading-none bg-gradient-to-br from-white via-slate-200 to-slate-400 bg-clip-text text-transparent mb-5">
          remapd
        </h1>
        <p className="text-slate-400 text-base max-w-xl leading-relaxed">
          Improving equity by bringing transparency to congressional district boundaries.
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

    </main>
  );
}
