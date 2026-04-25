"use client";

import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { API_BASE } from "@/lib/api";

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
  const [optimizedStates, setOptimizedStates] = useState<string[]>([]);
  const [resetting, setResetting] = useState<string | null>(null);

  const poll = async () => {
    try {
      const [mRes, pRes] = await Promise.all([
        fetch(`${API_BASE}/api/agent/metrics`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/agent/all-plans`, { cache: "no-store" }),
      ]);
      if (mRes.ok) setMetrics(await mRes.json());
      if (pRes.ok) {
        const plans = await pRes.json();
        setOptimizedStates(Object.keys(plans).sort());
      }
    } catch {
      // backend not ready yet
    }
  };

  useEffect(() => {
    let dead = false;
    const safePoll = async () => { if (!dead) await poll(); };
    safePoll();
    const t = setInterval(safePoll, 3500);
    return () => {
      dead = true;
      clearInterval(t);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleReset = async (abbr: string) => {
    setResetting(abbr);
    try {
      await fetch(`${API_BASE}/api/agent/plans/${abbr}`, { method: "DELETE" });
      await poll();
    } catch {
      // ignore
    } finally {
      setResetting(null);
    }
  };

  const stateCount = optimizedStates.length;
  const hasRun = metrics?.improvement != null &&
    typeof metrics.optimizedReward === "number" &&
    typeof metrics.baselineReward === "number";

  if (!hasRun) {
    return (
      <div className="w-full max-w-5xl mx-auto mt-6 rounded-2xl border border-white/10 bg-slate-900/50 px-8 py-7 text-center">
        <p className="text-sm text-white/30">
          No optimizations run yet — click a state and hit{" "}
          <span className="text-indigo-400 font-medium">Run Optimizer</span> to see nationwide results here.
        </p>
      </div>
    );
  }

  const { improvement, socialImpactScores, baselineSocialImpactScores, optimizedReward, baselineReward, state_abbr } = metrics!;

  return (
    <div className="w-full max-w-5xl mx-auto mt-6 rounded-2xl border border-white/10 bg-slate-900/50 px-8 py-7 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-white/30 font-semibold mb-1">
            Optimizer Results
          </p>
          <p className="text-xl font-bold text-white/90">
            {stateCount > 0 ? `${stateCount} state${stateCount > 1 ? "s" : ""} optimized` : "Latest run"}
            {state_abbr && (
              <span className="text-base text-white/40 font-normal ml-2">
                · most recent: <span className="text-indigo-400 font-medium">{state_abbr}</span>
              </span>
            )}
          </p>
          {/* Per-state reset chips */}
          {stateCount > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {optimizedStates.map((abbr) => (
                <div
                  key={abbr}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-xs font-mono text-indigo-300"
                >
                  {abbr}
                  <button
                    onClick={() => handleReset(abbr)}
                    disabled={resetting === abbr}
                    title={`Reset ${abbr} to real district boundaries`}
                    className="ml-0.5 text-white/30 hover:text-red-400 transition-colors disabled:opacity-40"
                  >
                    {resetting === abbr ? (
                      <span className="w-3 h-3 rounded-full border border-white/30 border-t-white animate-spin inline-block" />
                    ) : (
                      <RotateCcw size={11} />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        {typeof optimizedReward === "number" && typeof baselineReward === "number" && (
          <div className="text-right shrink-0">
            <p className="text-[11px] text-white/30 uppercase tracking-wider mb-1">Weighted Reward</p>
            <p className="text-xl font-mono font-bold text-white/90">
              {baselineReward.toFixed(3)}
              <span className="text-white/25 mx-2 font-normal">→</span>
              {optimizedReward.toFixed(3)}
              {improvement && (
                <span className={`text-base ml-2 ${improvement.total_reward_delta >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                  ({improvement.total_reward_delta >= 0 ? "+" : ""}{improvement.total_reward_delta.toFixed(3)})
                </span>
              )}
            </p>
          </div>
        )}
      </div>

      {/* Score breakdown grid */}
      <div className="grid grid-cols-4 gap-4">
        {SCORE_KEYS.map(([key, label]) => {
          const baseline = baselineSocialImpactScores?.[key];
          const optimized = socialImpactScores?.[key];
          const comp = improvement?.components[key];
          if (optimized === undefined) return null;
          return (
            <div key={key} className="rounded-xl border border-white/10 bg-white/5 px-5 py-4 space-y-2">
              <p className="text-[11px] text-white/35 uppercase tracking-wider font-semibold">{label}</p>
              <p className="text-3xl font-bold text-white/95 leading-none">
                {(optimized * 100).toFixed(1)}
                <span className="text-sm text-white/30 font-normal ml-0.5">%</span>
              </p>
              {baseline !== undefined && comp ? (
                <p className="text-xs font-mono">
                  <span className="text-white/35">{(baseline * 100).toFixed(1)}% → </span>
                  <Delta val={comp.delta} />
                  {comp.pct_vs_baseline != null && (
                    <span className="text-white/25 ml-1 text-[10px]">
                      ({comp.pct_vs_baseline >= 0 ? "+" : ""}{comp.pct_vs_baseline}%)
                    </span>
                  )}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-white/20">
        Baseline = round-robin initial district labels · delta reflects RL agent improvement over that starting point
      </p>
    </div>
  );
}
