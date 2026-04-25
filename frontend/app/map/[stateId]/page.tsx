import { notFound } from "next/navigation";

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
  "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
  "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
  "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
];

interface StatePageProps {
  params: Promise<{ stateId: string }>;
}

export default async function StatePage({ params }: StatePageProps) {
  const { stateId } = await params;
  const state = stateId.toUpperCase();

  if (!US_STATES.includes(state)) notFound();

  return (
    <main className="flex min-h-screen flex-col items-center justify-start p-8">
      <h1 className="text-3xl font-bold mb-4">State: {state}</h1>
      <p className="text-muted-foreground text-sm mb-8">
        Detailed redistricting view — RL agent output and social impact metrics will render here.
      </p>
      {/* TODO: Embed zoomed D3 district map for {state} */}
      {/* TODO: Embed RLMetricsPanel for {state} */}
      <div className="w-full max-w-4xl h-96 rounded-xl border border-dashed border-border flex items-center justify-center text-muted-foreground">
        District map for {state} (D3 zoom view — coming soon)
      </div>
    </main>
  );
}

export function generateStaticParams() {
  return US_STATES.map((stateId) => ({ stateId: stateId.toLowerCase() }));
}
