"use client";

/**
 * RLMetricsPanel — sidebar dashboard for real-time RL training metrics.
 *
 * Implementation checklist (TODO):
 *  1. Poll /api/metrics (FastAPI) every N seconds via SWR or React Query
 *  2. Render reward curve with Recharts <LineChart>
 *  3. Render entropy trend with Recharts <AreaChart>
 *  4. Render social impact score breakdown with <BarChart>
 *  5. Add episode counter and convergence indicator badge
 */

import { BarChart2, TrendingUp, Activity } from "lucide-react";

export interface RLMetrics {
  episode: number;
  reward: number[];
  entropy: number[];
  socialImpactScores: {
    racial_fairness: number;
    population_equality: number;
    compactness: number;
    voting_rights: number;
  };
}

interface RLMetricsPanelProps {
  metrics?: RLMetrics;
}

function MetricPlaceholder({ label, icon: Icon }: { label: string; icon: React.ElementType }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <Icon size={14} />
        {label}
      </div>
      <div className="w-full h-24 rounded-lg border border-dashed border-border bg-muted/30 flex items-center justify-center text-xs text-muted-foreground">
        Chart — coming soon
      </div>
    </div>
  );
}

export default function RLMetricsPanel({ metrics: _metrics }: RLMetricsPanelProps) {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-base font-semibold">RL Metrics</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Episode 0 — waiting for agent</p>
      </div>

      <MetricPlaceholder label="Cumulative Reward" icon={TrendingUp} />
      <MetricPlaceholder label="Policy Entropy" icon={Activity} />
      <MetricPlaceholder label="Social Impact Scores" icon={BarChart2} />

      {/* Social impact score pills (static placeholders) */}
      <div className="flex flex-col gap-2">
        {["Racial Fairness", "Pop. Equality", "Compactness", "Voting Rights"].map((label) => (
          <div key={label} className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono text-foreground">—</span>
          </div>
        ))}
      </div>
    </div>
  );
}
