"use client";

import { useState, useRef } from "react";
import { Sparkles, ChevronRight, RotateCcw } from "lucide-react";

export interface SuggestedParams {
  racial_weight: number;
  population_weight: number;
  compactness_weight: number;
  vra_weight: number;
  n_steps: number;
}

export interface AgentSuggestion {
  suggested_params: SuggestedParams;
  engine_agent: string;
  civil_rights_agent: string;
  legislative_agent: string;
  summary: string;
  model: string;
  powered_by: string;
}

interface AgentPromptBoxProps {
  stateAbbr: string;
  currentParams: Record<string, number>;
  onApply: (params: SuggestedParams) => void;
}

const SECTIONS = [
  { key: "engine_agent",       label: "Engine Agent",              accent: "text-sky-400" },
  { key: "civil_rights_agent", label: "Civil Rights Advocate Agent", accent: "text-emerald-400" },
  { key: "legislative_agent",  label: "Legislative Agent",          accent: "text-violet-400" },
  { key: "summary",            label: "Summary",                    accent: "text-amber-400" },
] as const;

const QUICK_PROMPTS = [
  "Prioritize minority representation",
  "Make districts more compact",
  "Maximize voting rights protections",
  "Balance population equally",
];

const WEIGHT_KEYS: { key: keyof SuggestedParams; label: string }[] = [
  { key: "racial_weight",      label: "Racial Fairness" },
  { key: "population_weight",  label: "Pop. Equality" },
  { key: "compactness_weight", label: "Compactness" },
  { key: "vra_weight",         label: "Voting Rights" },
];

export default function AgentPromptBox({
  stateAbbr,
  currentParams,
  onApply,
}: AgentPromptBoxProps) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestion, setSuggestion] = useState<AgentSuggestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const prevParamsRef = useRef<Record<string, number> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const submit = async (text: string) => {
    if (!text.trim() || loading) return;
    setLoading(true);
    setError(null);
    setSuggestion(null);
    setApplied(false);
    prevParamsRef.current = null;
    try {
      const res = await fetch("http://localhost:8000/api/agent/suggest-params", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          state_abbr: stateAbbr,
          prompt: text.trim(),
          current_params: currentParams,
        }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setSuggestion(await res.json());
    } catch {
      setError("Could not reach the agent. Is the backend running on port 8000?");
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (!suggestion) return;
    prevParamsRef.current = { ...currentParams };
    onApply(suggestion.suggested_params);
    setApplied(true);
  };

  const handleRevert = () => {
    if (!prevParamsRef.current) return;
    onApply(prevParamsRef.current as SuggestedParams);
    setApplied(false);
    prevParamsRef.current = null;
  };

  return (
    <div className="rounded-xl border border-indigo-500/25 bg-slate-900/80 overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-indigo-500/15 bg-indigo-500/5">
        <Sparkles size={13} className="text-indigo-400 shrink-0" />
        <span className="text-xs font-semibold text-indigo-300 tracking-wide">
          Ask the Agent
        </span>
        <span className="ml-auto text-[10px] text-white/25 font-mono">
          {suggestion?.powered_by === "claude" ? `✦ ${suggestion.model}` : "Claude · suggest params"}
        </span>
      </div>

      <div className="p-5 space-y-4">
        {/* Input */}
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit(prompt)}
            placeholder='e.g. "prioritize minority voting rights for this state"'
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white/80 placeholder-white/25 outline-none focus:border-indigo-500/50 transition-colors"
          />
          <button
            onClick={() => submit(prompt)}
            disabled={loading || !prompt.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 transition-colors shrink-0"
          >
            {loading ? (
              <>
                <span className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                Thinking…
              </>
            ) : (
              <>Ask <ChevronRight size={13} /></>
            )}
          </button>
        </div>

        {/* Quick prompts */}
        {!suggestion && !loading && (
          <div className="flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                onClick={() => { setPrompt(q); submit(q); }}
                className="px-3 py-1.5 rounded-full border border-white/10 bg-white/5 text-xs text-white/45 hover:text-white/80 hover:border-indigo-500/40 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-red-400 bg-red-500/10 rounded-lg px-4 py-3">{error}</p>
        )}

        {/* Agent response */}
        {suggestion && (
          <div className="space-y-4">
            {/* Four structured sections */}
            <div className="rounded-xl border border-white/10 bg-white/3 divide-y divide-white/8 overflow-hidden">
              {SECTIONS.map(({ key, label, accent }) => {
                const text = suggestion[key as keyof AgentSuggestion] as string;
                if (!text) return null;
                return (
                  <div key={key} className="px-5 py-4 space-y-1.5">
                    <p className={`text-[10px] font-bold uppercase tracking-widest ${accent}`}>
                      {label}
                    </p>
                    <p className="text-sm text-white/75 leading-relaxed">{text}</p>
                  </div>
                );
              })}
            </div>

            {/* Parameter diff grid */}
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-white/30 mb-2.5">
                Suggested weight changes
              </p>
              <div className="grid grid-cols-4 gap-2">
                {WEIGHT_KEYS.map(({ key, label }) => {
                  const suggested = suggestion.suggested_params[key] as number;
                  const current = (currentParams[key] as number) ?? 0;
                  const delta = suggested - current;
                  const changed = Math.abs(delta) > 0.005;
                  return (
                    <div
                      key={key}
                      className={`rounded-lg px-3 py-2.5 border text-center space-y-1 ${
                        changed
                          ? "border-indigo-500/35 bg-indigo-500/10"
                          : "border-white/8 bg-white/4"
                      }`}
                    >
                      <p className="text-[10px] text-white/40 leading-tight">{label}</p>
                      <p className="text-base font-bold text-white/90 leading-none">
                        {suggested.toFixed(2)}
                      </p>
                      {changed ? (
                        <p className={`text-[10px] font-mono ${delta > 0 ? "text-emerald-400" : "text-amber-400"}`}>
                          {delta > 0 ? "+" : ""}{delta.toFixed(2)}
                        </p>
                      ) : (
                        <p className="text-[10px] text-white/20">—</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3">
              {!applied ? (
                <button
                  onClick={handleApply}
                  className="flex-1 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors"
                >
                  Apply to optimizer sliders
                </button>
              ) : (
                <div className="flex-1 flex items-center gap-3">
                  <div className="flex items-center gap-2 text-sm text-emerald-400 font-medium">
                    <span className="w-4 h-4 rounded-full bg-emerald-500/20 flex items-center justify-center text-[10px]">✓</span>
                    Applied to sliders
                  </div>
                  <button
                    onClick={handleRevert}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/15 text-xs text-white/50 hover:bg-white/5 transition-colors ml-auto"
                  >
                    <RotateCcw size={11} />
                    Revert
                  </button>
                </div>
              )}
              <button
                onClick={() => { setSuggestion(null); setPrompt(""); setApplied(false); prevParamsRef.current = null; inputRef.current?.focus(); }}
                className="px-3 py-2.5 rounded-lg border border-white/10 text-xs text-white/35 hover:text-white/70 transition-colors"
              >
                Clear
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
