"use client";

import { useEffect, useState } from "react";
import { Users, DollarSign, GraduationCap, TrendingDown, AlertCircle } from "lucide-react";
import { API_BASE } from "@/lib/api";

interface Demographics {
  state_name: string;
  fips: string;
  total_population: number;
  white_pct: number;
  black_pct: number;
  asian_pct: number;
  hispanic_pct: number;
  other_pct: number;
  median_household_income: number;
  college_degree_pct: number;
  poverty_rate: number;
  median_age: number;
}

interface DemographicsPanelProps {
  stateAbbr: string;
}

function RaceBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs">
        <span className="text-white/50">{label}</span>
        <span className="font-mono font-medium text-white/80">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-white/10 p-2.5 bg-white/5">
      <Icon size={14} className="mt-0.5 text-white/40 shrink-0" />
      <div>
        <p className="text-[10px] text-white/40 leading-tight">{label}</p>
        <p className="text-sm font-semibold leading-tight text-white/90">{value}</p>
      </div>
    </div>
  );
}

export default function DemographicsPanel({ stateAbbr }: DemographicsPanelProps) {
  const [data, setData] = useState<Demographics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/states/${stateAbbr}/demographics`)
      .then((r) => {
        if (!r.ok) throw new Error(`API error ${r.status}`);
        return r.json();
      })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, [stateAbbr]);

  if (loading) return (
    <div className="space-y-2">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="h-8 rounded bg-white/5 animate-pulse" />
      ))}
    </div>
  );

  if (error) return (
    <div className="flex items-start gap-2 text-xs text-red-400 p-3 rounded-lg border border-red-500/20 bg-red-500/10">
      <AlertCircle size={14} className="mt-0.5 shrink-0" />
      <div>
        <p className="font-medium">Could not load Census data</p>
        <p className="text-white/40 mt-0.5">Add CENSUS_API_KEY to backend/.env</p>
        <p className="text-white/30 mt-0.5 font-mono">{error}</p>
      </div>
    </div>
  );

  if (!data) return null;

  const noKey = data.total_population === 0;

  return (
    <div className="space-y-4">
      {noKey && (
        <div className="text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
          No Census API key set — showing empty data. Add <code className="font-mono">CENSUS_API_KEY</code> to <code className="font-mono">backend/.env</code>.
        </div>
      )}

      {/* Key stats */}
      <div className="grid grid-cols-2 gap-2">
        <StatCard icon={Users} label="Total Population" value={data.total_population.toLocaleString()} />
        <StatCard icon={DollarSign} label="Median Income" value={data.median_household_income > 0 ? `$${data.median_household_income.toLocaleString()}` : "—"} />
        <StatCard icon={GraduationCap} label="College Degree" value={data.college_degree_pct > 0 ? `${data.college_degree_pct}%` : "—"} />
        <StatCard icon={TrendingDown} label="Poverty Rate" value={data.poverty_rate > 0 ? `${data.poverty_rate}%` : "—"} />
      </div>

      {/* Median age */}
      {data.median_age > 0 && (
        <div className="text-xs text-white/40">
          Median age: <span className="font-semibold text-white/80">{data.median_age}</span>
        </div>
      )}

      {/* Race / ethnicity breakdown */}
      <div>
        <p className="text-xs font-medium mb-2 text-white/70">Racial / Ethnic Composition</p>
        <div className="space-y-2">
          <RaceBar label="White" pct={data.white_pct} color="#6366f1" />
          <RaceBar label="Hispanic / Latino" pct={data.hispanic_pct} color="#f59e0b" />
          <RaceBar label="Black / African American" pct={data.black_pct} color="#10b981" />
          <RaceBar label="Asian" pct={data.asian_pct} color="#3b82f6" />
          <RaceBar label="Other / Multi-racial" pct={data.other_pct} color="#8b5cf6" />
        </div>
      </div>

      <p className="text-[10px] text-white/25">
        Source: US Census Bureau ACS 5-Year Estimates (2022)
      </p>
    </div>
  );
}
