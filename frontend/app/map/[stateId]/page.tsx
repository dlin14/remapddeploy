import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import StateMap from "@/components/map/StateMap";
import DemographicsPanel from "@/components/dashboard/DemographicsPanel";
import RLParamsSliders from "@/components/dashboard/RLParamsSliders";

const STATE_INFO: Record<string, { name: string; fips: string }> = {
  AL: { name: "Alabama", fips: "01" },
  AK: { name: "Alaska", fips: "02" },
  AZ: { name: "Arizona", fips: "04" },
  AR: { name: "Arkansas", fips: "05" },
  CA: { name: "California", fips: "06" },
  CO: { name: "Colorado", fips: "08" },
  CT: { name: "Connecticut", fips: "09" },
  DE: { name: "Delaware", fips: "10" },
  DC: { name: "District of Columbia", fips: "11" },
  FL: { name: "Florida", fips: "12" },
  GA: { name: "Georgia", fips: "13" },
  HI: { name: "Hawaii", fips: "15" },
  ID: { name: "Idaho", fips: "16" },
  IL: { name: "Illinois", fips: "17" },
  IN: { name: "Indiana", fips: "18" },
  IA: { name: "Iowa", fips: "19" },
  KS: { name: "Kansas", fips: "20" },
  KY: { name: "Kentucky", fips: "21" },
  LA: { name: "Louisiana", fips: "22" },
  ME: { name: "Maine", fips: "23" },
  MD: { name: "Maryland", fips: "24" },
  MA: { name: "Massachusetts", fips: "25" },
  MI: { name: "Michigan", fips: "26" },
  MN: { name: "Minnesota", fips: "27" },
  MS: { name: "Mississippi", fips: "28" },
  MO: { name: "Missouri", fips: "29" },
  MT: { name: "Montana", fips: "30" },
  NE: { name: "Nebraska", fips: "31" },
  NV: { name: "Nevada", fips: "32" },
  NH: { name: "New Hampshire", fips: "33" },
  NJ: { name: "New Jersey", fips: "34" },
  NM: { name: "New Mexico", fips: "35" },
  NY: { name: "New York", fips: "36" },
  NC: { name: "North Carolina", fips: "37" },
  ND: { name: "North Dakota", fips: "38" },
  OH: { name: "Ohio", fips: "39" },
  OK: { name: "Oklahoma", fips: "40" },
  OR: { name: "Oregon", fips: "41" },
  PA: { name: "Pennsylvania", fips: "42" },
  RI: { name: "Rhode Island", fips: "44" },
  SC: { name: "South Carolina", fips: "45" },
  SD: { name: "South Dakota", fips: "46" },
  TN: { name: "Tennessee", fips: "47" },
  TX: { name: "Texas", fips: "48" },
  UT: { name: "Utah", fips: "49" },
  VT: { name: "Vermont", fips: "50" },
  VA: { name: "Virginia", fips: "51" },
  WA: { name: "Washington", fips: "53" },
  WV: { name: "West Virginia", fips: "54" },
  WI: { name: "Wisconsin", fips: "55" },
  WY: { name: "Wyoming", fips: "56" },
};

interface StatePageProps {
  params: Promise<{ stateId: string }>;
}

export default async function StatePage({ params }: StatePageProps) {
  const { stateId } = await params;
  const abbr = stateId.toUpperCase();
  const info = STATE_INFO[abbr];
  if (!info) notFound();

  return (
    <div className="flex flex-col min-h-screen bg-background">
      {/* Top bar */}
      <header className="flex items-center gap-3 px-6 py-3 border-b border-border bg-background/80 backdrop-blur sticky top-0 z-20">
        <Link
          href="/"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft size={14} />
          All States
        </Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-semibold">{info.name}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          FIPS: {info.fips} · {abbr}
        </span>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Map — center */}
        <main className="flex-1 p-6 overflow-auto">
          <StateMap stateFips={info.fips} stateName={info.name} />
        </main>

        {/* Sidebar */}
        <aside className="w-80 border-l border-border flex flex-col overflow-y-auto">
          {/* Demographics */}
          <div className="p-4 border-b border-border">
            <h2 className="text-sm font-semibold mb-3">Demographics</h2>
            <DemographicsPanel stateAbbr={abbr} />
          </div>

          {/* RL Parameters */}
          <div className="p-4">
            <h2 className="text-sm font-semibold mb-3">RL Parameters</h2>
            <RLParamsSliders stateAbbr={abbr} />
          </div>
        </aside>
      </div>
    </div>
  );
}

export function generateStaticParams() {
  return Object.keys(STATE_INFO).map((abbr) => ({ stateId: abbr.toLowerCase() }));
}
