"use client";

import { useEffect, useState } from "react";

interface ScoreComponents {
  racial_fairness: number;
  population_equality: number;
  compactness: number;
  voting_rights: number;
}

interface Metrics {
  state_abbr?: string;
  optimizedReward?: number;
  baselineReward?: number;
  socialImpactScores: ScoreComponents;
  baselineSocialImpactScores?: ScoreComponents;
  improvement?: {
    total_reward_delta: number;
    total_reward_pct_vs_baseline: number | null;
    components: Record<string, { delta: number; pct_vs_baseline: number | null }>;
  } | null;
}

const SCORE_KEYS: [keyof ScoreComponents, string][] = [
  ["racial_fairness", "Racial Fairness"],
  ["population_equality", "Pop. Equality"],
  ["compactness", "Compactness"],
  ["voting_rights", "Voting Rights"],
];

function Delta({ val }: { val: number }) {
  const pos = val >= 0;
  return (
    <span className={pos ? "text-emerald-400" : "text-amber-400"}>
      {pos ? "+" : ""}
      {(val * 100).toFixed(1)}pp
    </span>
  );
}

export default function NationwideStatsPanel() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [stateCount, setStateCount] = useState(0);

  useEffect(() => {
    let dead = false;
    const poll = async () => {
      try {
        const [mRes, pRes] = await Promise.all([
          fetch("http://localhost:8000/api/agent/metrics", { cache: "no-store" }),
          fetch("http://localhost:8000/api/agent/all-plans", { cache: "no-store" }),
        ]);
        if (mRes.ok && !dead) setMetrics(await mRes.json());
        if (pRes.ok && !dead) setStateCount(Object.keys(await pRes.json()).length);
      } catch {
        // backend not ready yet
      }
    };
    poll();
    const t = setInterval(poll, 3500);
    return () => {
      dead = true;
      clearInterval(t);
    };
  }, []);

  const hasRun = metrics?.improvement != null &&
    typeof metrics.optimizedReward === "number" &&
    typeof metrics.baselineReward === "number";

  if (!hasRun) {
    return (
      <div className="w-full max-w-5xl mx-auto mt-4 rounded-xl border border-white/10 bg-slate-900/50 px-6 py-5 text-center">
        <p className="text-xs text-white/30">
          No optimizations run yet — click a state and hit <span className="text-indigo-400">Run Optimizer</span> to see results here.
        </p>
      </div>
    );
  }

  const { improvement, socialImpactScores, baselineSocialImpactScores, optimizedReward, baselineReward, state_abbr } = metrics!;

  return (
    <div className="w-full max-w-5xl mx-auto mt-4 rounded-xl border border-white/10 bg-slate-900/50 px-6 py-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-white/30 font-medium">Optimizer Results</p>
          <p className="text-sm font-semibold text-white/85 mt-0.5">
            {stateCount > 0 ? `${stateCount} state${stateCount > 1 ? "s" : ""} optimized` : "Latest run"}
            {state_abbr ? <span className="text-white/40 font-normal"> · most recent: <span className="text-indigo-400">{state_abbr}</span></span> : null}
          </p>
        </div>
        {typeof optimizedReward === "number" && typeof baselineReward === "number" && (
          <div className="text-right">
            <p className="text-[10px] text-white/30 uppercase tracking-wider">Weighted Reward</p>
            <p className="text-sm font-mono text-white/80 mt-0.5">
              {baselineReward.toFixed(3)}
              <span className="text-white/30 mx-1">→</span>
              {optimizedReward.toFixed(3)}
              {improvement && (
                <span className={improvement.total_reward_delta >= 0 ? " text-emerald-400" : " text-amber-400"}>
                  {" "}({improvement.total_reward_delta >= 0 ? "+" : ""}{improvement.total_reward_delta.toFixed(3)})
                </span>
              )}
            </p>
          </div>
        )}
      </div>

      {/* Score breakdown grid */}
      <div className="grid grid-cols-4 gap-3">
        {SCORE_KEYS.map(([key, label]) => {
          const baseline = baselineSocialImpactScores?.[key];
          const optimized = socialImpactScores?.[key];
          const comp = improvement?.components[key];
          if (optimized === undefined) return null;
          return (
            <div key={key} className="rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 space-y-1">
              <p className="text-[10px] text-white/35 uppercase tracking-wider font-medium">{label}</p>
              <p className="text-lg font-bold text-white/90 leading-none">
                {(optimized * 100).toFixed(1)}
                <span className="text-xs text-white/30 font-normal">%</span>
              </p>
              {baseline !== undefined && comp ? (
                <p className="text-[10px] font-mono">
                  <Delta val={comp.delta} />
                  {comp.pct_vs_baseline != null && (
                    <span className="text-white/25 ml-1">
                      ({comp.pct_vs_baseline >= 0 ? "+" : ""}{comp.pct_vs_baseline}% vs baseline)
                    </span>
                  )}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-white/20">
        Baseline = round-robin initial district labels · improvements reflect optimizer gain over that starting point
      </p>
    </div>
  );
}
