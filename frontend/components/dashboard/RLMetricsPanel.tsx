"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart2, TrendingUp, Activity } from "lucide-react";
import { API_BASE } from "@/lib/api";

export interface ScoreComponents {
  racial_fairness: number;
  population_equality: number;
  compactness: number;
  voting_rights: number;
}

export interface RLMetrics {
  episode: number;
  reward: number[];
  entropy: number[];
  socialImpactScores: ScoreComponents;
  baselineSocialImpactScores?: ScoreComponents;
  baselineReward?: number;
  optimizedReward?: number;
  baselineLabel?: string;
  improvement?: {
    total_reward_delta: number;
    total_reward_pct_vs_baseline: number | null;
    components: Record<
      string,
      { delta: number; pct_vs_baseline: number | null }
    >;
  } | null;
  state_abbr?: string;
}

interface RLMetricsPanelProps {
  metrics?: RLMetrics;
}

function MetricCard({
  label,
  icon: Icon,
  value,
}: {
  label: string;
  icon: React.ElementType;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <Icon size={14} />
        {label}
      </div>
      <div className="w-full h-12 rounded-lg border border-border bg-muted/30 flex items-center justify-center text-xs text-muted-foreground font-mono">
        {value}
      </div>
    </div>
  );
}

export default function RLMetricsPanel({ metrics: _metrics }: RLMetricsPanelProps) {
  const [metrics, setMetrics] = useState<RLMetrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/agent/metrics`, { cache: "no-store" });
        if (!resp.ok) return;
        const data = (await resp.json()) as RLMetrics;
        if (!cancelled) setMetrics(data);
      } catch {
        // Keep panel stable when backend is down.
      }
    };
    poll();
    const timer = setInterval(poll, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const latestReward = useMemo(() => {
    if (!metrics || metrics.reward.length === 0) return "—";
    return metrics.reward[metrics.reward.length - 1].toFixed(4);
  }, [metrics]);

  const latestExploration = useMemo(() => {
    if (!metrics || metrics.entropy.length === 0) return "—";
    return metrics.entropy[metrics.entropy.length - 1].toFixed(4);
  }, [metrics]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-base font-semibold">RL Metrics</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Iteration {metrics?.episode ?? 0} — reward-driven optimizer
        </p>
      </div>

      <MetricCard label="Current Reward" icon={TrendingUp} value={latestReward} />
      <MetricCard label="Exploration Rate" icon={Activity} value={latestExploration} />
      <MetricCard
        label="Best Social Score"
        icon={BarChart2}
        value={
          metrics
            ? (
                metrics.socialImpactScores.racial_fairness * 0.35 +
                metrics.socialImpactScores.population_equality * 0.3 +
                metrics.socialImpactScores.compactness * 0.2 +
                metrics.socialImpactScores.voting_rights * 0.15
              ).toFixed(4)
            : "—"
        }
      />

      {/* Social impact score pills (static placeholders) */}
      <div className="flex flex-col gap-2">
        {["Racial Fairness", "Pop. Equality", "Compactness", "Voting Rights"].map((label) => (
          <div key={label} className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono text-foreground">
              {metrics
                ? ({
                    "Racial Fairness": metrics.socialImpactScores.racial_fairness,
                    "Pop. Equality": metrics.socialImpactScores.population_equality,
                    Compactness: metrics.socialImpactScores.compactness,
                    "Voting Rights": metrics.socialImpactScores.voting_rights,
                  }[label] ?? 0
                ).toFixed(3)
                : "—"}
            </span>
          </div>
        ))}
      </div>

      {metrics?.improvement &&
        metrics.baselineSocialImpactScores &&
        typeof metrics.baselineReward === "number" &&
        typeof metrics.optimizedReward === "number" && (
          <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
            <div>
              <p className="text-xs font-semibold text-foreground">Improvement vs baseline</p>
              <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                Baseline = round-robin initial district labels (synthetic). This is not the official
                congressional map — it is the starting point the optimizer improves from.
              </p>
            </div>
            <div className="text-[11px] font-mono flex flex-col gap-1 border-b border-border pb-2">
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground shrink-0">Weighted reward</span>
                <span className="text-right">
                  {metrics.baselineReward.toFixed(3)} → {metrics.optimizedReward.toFixed(3)}
                  <span
                    className={
                      metrics.improvement.total_reward_delta >= 0
                        ? " text-emerald-700"
                        : " text-amber-800"
                    }
                  >
                    {" "}
                    ({metrics.improvement.total_reward_delta >= 0 ? "+" : ""}
                    {metrics.improvement.total_reward_delta.toFixed(3)})
                  </span>
                  {metrics.improvement.total_reward_pct_vs_baseline != null && (
                    <span className="text-muted-foreground">
                      {" "}
                      ({metrics.improvement.total_reward_pct_vs_baseline >= 0 ? "+" : ""}
                      {metrics.improvement.total_reward_pct_vs_baseline}% vs baseline)
                    </span>
                  )}
                </span>
              </div>
            </div>
            <div className="space-y-1.5">
              {(
                [
                  ["racial_fairness", "Racial fairness"],
                  ["population_equality", "Pop. equality"],
                  ["compactness", "Compactness"],
                  ["voting_rights", "Voting rights"],
                ] as const
              ).map(([key, title]) => {
                const base = metrics.baselineSocialImpactScores![key];
                const opt = metrics.socialImpactScores[key];
                const comp = metrics.improvement!.components[key];
                if (!comp) return null;
                const pct =
                  comp.pct_vs_baseline != null
                    ? `${comp.pct_vs_baseline >= 0 ? "+" : ""}${comp.pct_vs_baseline}%`
                    : "—";
                return (
                  <div key={key} className="text-[10px] leading-tight">
                    <div className="font-medium text-foreground">{title}</div>
                    <div className="font-mono text-muted-foreground mt-0.5">
                      {base.toFixed(3)} → {opt.toFixed(3)}
                      <span className={comp.delta >= 0 ? " text-emerald-700" : " text-amber-800"}>
                        {" "}
                        (Δ {comp.delta >= 0 ? "+" : ""}
                        {comp.delta.toFixed(3)}, {pct} vs baseline)
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
    </div>
  );
}
