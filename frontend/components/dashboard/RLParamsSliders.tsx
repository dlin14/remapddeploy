"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Play, RotateCcw, Cpu } from "lucide-react";

// 118th Congress apportionment
const ABBR_TO_DISTRICTS: Record<string, number> = {
  AL: 7,  AK: 1,  AZ: 9,  AR: 4,  CA: 52, CO: 8,  CT: 5,  DE: 1,  DC: 1,
  FL: 28, GA: 14, HI: 2,  ID: 2,  IL: 17, IN: 9,  IA: 4,  KS: 4,  KY: 6,
  LA: 6,  ME: 2,  MD: 8,  MA: 9,  MI: 13, MN: 8,  MS: 4,  MO: 8,  MT: 2,
  NE: 3,  NV: 4,  NH: 2,  NJ: 12, NM: 3,  NY: 26, NC: 14, ND: 1,  OH: 15,
  OK: 5,  OR: 6,  PA: 17, RI: 2,  SC: 7,  SD: 1,  TN: 9,  TX: 38, UT: 4,
  VT: 1,  VA: 11, WA: 10, WV: 2,  WI: 8,  WY: 1,
};

interface RLParams {
  learning_rate: number;
  gamma: number;
  n_districts: number;
  ent_coef: number;
  n_steps: number;
  racial_weight: number;
  population_weight: number;
  compactness_weight: number;
  vra_weight: number;
}

const BASE_DEFAULTS: Omit<RLParams, "n_districts"> = {
  learning_rate: 3e-4,
  gamma: 0.99,
  ent_coef: 0.01,
  n_steps: 2048,
  racial_weight: 0.35,
  population_weight: 0.30,
  compactness_weight: 0.20,
  vra_weight: 0.15,
};

interface SliderRowProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}

function SliderRow({ label, value, min, max, step, format, onChange }: SliderRowProps) {
  const display = format ? format(value) : String(value);
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-white/50">{label}</span>
        <span className="text-xs font-mono font-medium text-white/80">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full accent-indigo-500 cursor-pointer"
      />
    </div>
  );
}

interface RLParamsSlidersProps {
  stateAbbr: string;
}

interface RunResponse {
  iterations?: number;
  best_reward?: number;
  baseline_reward?: number;
  improvement?: {
    total_reward_delta: number;
    total_reward_pct_vs_baseline: number | null;
    components: Record<string, { delta: number; pct_vs_baseline: number | null }>;
  };
  baseline_score_breakdown?: Record<string, number>;
  score_breakdown?: Record<string, number>;
}

export default function RLParamsSliders({ stateAbbr }: RLParamsSlidersProps) {
  const defaultDistricts = ABBR_TO_DISTRICTS[stateAbbr] ?? 5;
  const DEFAULTS: RLParams = { ...BASE_DEFAULTS, n_districts: defaultDistricts };
  const [params, setParams] = useState<RLParams>(DEFAULTS);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<RunResponse | null>(null);
  const runningRef = useRef(false);

  // Stop the optimizer when the user navigates away from the state page
  useEffect(() => {
    return () => {
      if (runningRef.current) {
        fetch("http://localhost:8000/api/agent/stop", {
          method: "POST",
          keepalive: true,
        }).catch(() => {});
      }
    };
  }, []);

  const set = useCallback(<K extends keyof RLParams>(key: K, val: RLParams[K]) => {
    setParams((p) => ({ ...p, [key]: val }));
  }, []);

  const rewardWeightTotal = (
    params.racial_weight + params.population_weight +
    params.compactness_weight + params.vra_weight
  ).toFixed(2);

  const handleRun = async () => {
    setRunning(true);
    runningRef.current = true;
    setStatus("Starting optimizer...");
    try {
      const resp = await fetch("http://localhost:8000/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state_abbr: stateAbbr, ...params }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const payload = (await resp.json()) as RunResponse;
      setLastRun(payload);
      setStatus(
        `Optimization complete in ${payload.iterations ?? 0} iterations (best reward ${payload.best_reward ?? "n/a"})`
      );
    } catch {
      setStatus("Could not reach backend optimizer. Check API server on port 8000.");
    } finally {
      setRunning(false);
      runningRef.current = false;
    }
  };

  return (
    <div className="space-y-5">
      {/* RL hyperparameters */}
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-white/35">
          RL Hyperparameters
        </p>
        <SliderRow
          label="Learning Rate"
          value={params.learning_rate}
          min={1e-5} max={1e-2} step={1e-5}
          format={(v) => v.toExponential(1)}
          onChange={(v) => set("learning_rate", v)}
        />
        <SliderRow
          label="Discount Factor γ"
          value={params.gamma}
          min={0.80} max={0.999} step={0.001}
          format={(v) => v.toFixed(3)}
          onChange={(v) => set("gamma", v)}
        />
        <SliderRow
          label="Entropy Coefficient"
          value={params.ent_coef}
          min={0} max={0.1} step={0.001}
          format={(v) => v.toFixed(3)}
          onChange={(v) => set("ent_coef", v)}
        />
        <SliderRow
          label="Rollout Steps (n_steps)"
          value={params.n_steps}
          min={128} max={8192} step={128}
          format={(v) => v.toLocaleString()}
          onChange={(v) => set("n_steps", v)}
        />
        <SliderRow
          label="Number of Districts"
          value={params.n_districts}
          min={1} max={53} step={1}
          onChange={(v) => set("n_districts", v)}
        />
      </div>

      {/* Reward weights */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-white/35">
            Reward Weights
          </p>
          <span className={`text-[10px] font-mono ${Number(rewardWeightTotal) > 1.01 ? "text-red-400" : "text-white/35"}`}>
            Σ = {rewardWeightTotal}
          </span>
        </div>
        <SliderRow
          label="Racial Fairness"
          value={params.racial_weight}
          min={0} max={1} step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => set("racial_weight", v)}
        />
        <SliderRow
          label="Population Equality"
          value={params.population_weight}
          min={0} max={1} step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => set("population_weight", v)}
        />
        <SliderRow
          label="Compactness"
          value={params.compactness_weight}
          min={0} max={1} step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => set("compactness_weight", v)}
        />
        <SliderRow
          label="Voting Rights Act"
          value={params.vra_weight}
          min={0} max={1} step={0.01}
          format={(v) => v.toFixed(2)}
          onChange={(v) => set("vra_weight", v)}
        />
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button
          onClick={handleRun}
          disabled={running}
          className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 text-white text-xs font-medium py-2 hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          <Play size={12} />
          {running ? "Running…" : "Run Optimizer"}
        </button>
        <button
          onClick={() => {
            setParams(DEFAULTS);
            setStatus(null);
            setLastRun(null);
          }}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-white/15 px-3 py-2 text-xs text-white/60 hover:bg-white/5 transition-colors"
          title="Reset to defaults"
        >
          <RotateCcw size={12} />
        </button>
      </div>

      {status && (
        <div className="flex items-start gap-1.5 text-xs text-white/50 bg-white/5 rounded-lg px-3 py-2">
          <Cpu size={12} className="mt-0.5 shrink-0" />
          {status}
        </div>
      )}

      {lastRun?.improvement &&
        typeof lastRun.baseline_reward === "number" &&
        typeof lastRun.best_reward === "number" && (
          <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">
              Fairness vs baseline
            </p>
            <p className="text-[10px] text-white/30 leading-snug">
              Baseline = round-robin initial labels (not real congressional districts).
            </p>
            <div className="text-[11px] font-mono text-white/80">
              Reward {lastRun.baseline_reward.toFixed(3)} → {lastRun.best_reward.toFixed(3)}
              <span
                className={
                  lastRun.improvement.total_reward_delta >= 0 ? " text-emerald-400" : " text-amber-400"
                }
              >
                {" "}
                (Δ {lastRun.improvement.total_reward_delta >= 0 ? "+" : ""}
                {lastRun.improvement.total_reward_delta.toFixed(3)})
              </span>
              {lastRun.improvement.total_reward_pct_vs_baseline != null && (
                <span className="text-white/30">
                  {" "}
                  [{lastRun.improvement.total_reward_pct_vs_baseline >= 0 ? "+" : ""}
                  {lastRun.improvement.total_reward_pct_vs_baseline}% vs baseline]
                </span>
              )}
            </div>
            <div className="space-y-1 text-[10px] font-mono">
              {(
                [
                  ["racial_fairness", "Racial fairness"],
                  ["population_equality", "Pop. equality"],
                  ["compactness", "Compactness"],
                  ["voting_rights", "Voting rights"],
                ] as const
              ).map(([key, title]) => {
                const b = lastRun.baseline_score_breakdown?.[key];
                const o = lastRun.score_breakdown?.[key];
                const c = lastRun.improvement?.components[key];
                if (b === undefined || o === undefined || !c) return null;
                const pct =
                  c.pct_vs_baseline != null
                    ? `${c.pct_vs_baseline >= 0 ? "+" : ""}${c.pct_vs_baseline}%`
                    : "—";
                return (
                  <div key={key} className="leading-tight">
                    <span className="text-white/40">{title}: </span>
                    {b.toFixed(2)} → {o.toFixed(2)}
                    <span className={c.delta >= 0 ? " text-emerald-400" : " text-amber-400"}>
                      {" "}
                      (Δ {c.delta >= 0 ? "+" : ""}
                      {c.delta.toFixed(3)}, {pct})
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
    </div>
  );
}
