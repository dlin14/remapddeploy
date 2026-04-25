"use client";

import { useState, useRef } from "react";
import StateMap from "@/components/map/StateMap";
import DemographicsPanel from "@/components/dashboard/DemographicsPanel";
import RLParamsSliders from "@/components/dashboard/RLParamsSliders";
import AgentPromptBox, { type SuggestedParams } from "@/components/dashboard/AgentPromptBox";

interface StatePageClientProps {
  abbr: string;
  fips: string;
  name: string;
}

export default function StatePageClient({ abbr, fips, name }: StatePageClientProps) {
  // Shared agent-suggestion state — bridges AgentPromptBox (main col) → RLParamsSliders (sidebar)
  const [externalParams, setExternalParams] = useState<Partial<Record<string, number>> | undefined>();
  const [externalParamsKey, setExternalParamsKey] = useState(0);

  // Also track current slider state so AgentPromptBox can show accurate diffs
  const currentParamsRef = useRef<Record<string, number>>({
    racial_weight: 0.35,
    population_weight: 0.30,
    compactness_weight: 0.20,
    vra_weight: 0.15,
    n_steps: 700,
  });

  const handleAgentApply = (params: SuggestedParams) => {
    currentParamsRef.current = { ...currentParamsRef.current, ...params };
    setExternalParams(params);
    setExternalParamsKey((k) => k + 1);
  };

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Main column — map + agent prompt */}
      <main className="flex-1 flex flex-col gap-6 p-6 overflow-auto">
        <StateMap stateFips={fips} stateName={name} />

        <AgentPromptBox
          stateAbbr={abbr}
          currentParams={currentParamsRef.current}
          onApply={handleAgentApply}
        />
      </main>

      {/* Sidebar — demographics + RL sliders */}
      <aside className="w-80 border-l border-white/10 flex flex-col overflow-y-auto bg-slate-900/40">
        <div className="p-4 border-b border-white/10">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
            Demographics
          </h2>
          <DemographicsPanel stateAbbr={abbr} />
        </div>

        <div className="p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-white/40 mb-3">
            RL Parameters
          </h2>
          <RLParamsSliders
            stateAbbr={abbr}
            externalParams={externalParams}
            externalParamsKey={externalParamsKey}
          />
        </div>
      </aside>
    </div>
  );
}
