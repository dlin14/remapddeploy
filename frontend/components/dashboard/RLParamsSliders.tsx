"use client";

import { useState, useCallback } from "react";
import { Play, RotateCcw, Cpu } from "lucide-react";

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

const DEFAULTS: RLParams = {
  learning_rate: 3e-4,
  gamma: 0.99,
  n_districts: 5,
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
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-mono font-medium text-foreground">{display}</span>
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

export default function RLParamsSliders({ stateAbbr }: RLParamsSlidersProps) {
  const [params, setParams] = useState<RLParams>(DEFAULTS);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const set = useCallback(<K extends keyof RLParams>(key: K, val: RLParams[K]) => {
    setParams((p) => ({ ...p, [key]: val }));
  }, []);

  const rewardWeightTotal = (
    params.racial_weight + params.population_weight +
    params.compactness_weight + params.vra_weight
  ).toFixed(2);

  const handleRun = async () => {
    setRunning(true);
    setStatus("Starting agent...");
    try {
      const resp = await fetch("http://localhost:8000/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state_abbr: stateAbbr, ...params }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      setStatus("Agent running — check metrics panel");
    } catch {
      setStatus("Backend endpoint not yet implemented — scaffold complete");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* RL hyperparameters */}
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
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
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Reward Weights
          </p>
          <span className={`text-[10px] font-mono ${Number(rewardWeightTotal) > 1.01 ? "text-destructive" : "text-muted-foreground"}`}>
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
          {running ? "Running…" : "Run Agent"}
        </button>
        <button
          onClick={() => { setParams(DEFAULTS); setStatus(null); }}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs hover:bg-muted transition-colors"
          title="Reset to defaults"
        >
          <RotateCcw size={12} />
        </button>
      </div>

      {status && (
        <div className="flex items-start gap-1.5 text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
          <Cpu size={12} className="mt-0.5 shrink-0" />
          {status}
        </div>
      )}
    </div>
  );
}
