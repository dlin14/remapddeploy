import USMap from "@/components/map/USMap";
import RLMetricsPanel from "@/components/dashboard/RLMetricsPanel";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-row">
      {/* Main map area */}
      <section className="flex-1 flex flex-col items-center justify-center p-8">
        <h1 className="text-3xl font-bold mb-2">remapd</h1>
        <p className="text-muted-foreground text-sm mb-8">
          Reinforcement Learning–powered redistricting simulation
        </p>
        <USMap />
      </section>

      {/* RL Metrics sidebar */}
      <aside className="w-80 border-l border-border p-6 flex flex-col gap-4">
        <RLMetricsPanel />
      </aside>
    </main>
  );
}
