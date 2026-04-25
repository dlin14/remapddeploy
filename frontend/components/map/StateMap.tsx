"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import * as topojson from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";

interface StateMapProps {
  stateFips: string;
  stateName: string;
}

interface DistrictPlan {
  assignment: Record<string, number>;   // county_fips → optimizer district id
  district_metrics: Array<{
    district_id: number;
    num_counties: number;
    population: number;
    minority_share: number;
  }>;
  /** present only on cached optimizer runs */
  best_reward?: number;
}

const W = 700;
const H = 500;

export default function StateMap({ stateFips, stateName }: StateMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [plan, setPlan] = useState<DistrictPlan | null>(null);
  /** true once the user has actually run the optimizer for this state */
  const [optimizerRan, setOptimizerRan] = useState(false);

  const districtColor = useMemo(() => d3.scaleOrdinal(d3.schemeTableau10), []);
  const planRef = useRef<DistrictPlan | null>(null);
  const structureReadyRef = useRef(false);

  useEffect(() => { planRef.current = plan; }, [plan]);

  // ── Poll district plan ────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const loadPlan = async () => {
      try {
        const resp = await fetch(
          `http://localhost:8000/api/states/${stateFips}/district-plan`,
          { cache: "no-store" },
        );
        if (!resp.ok) return;
        const data = (await resp.json()) as DistrictPlan;
        if (!cancelled) {
          // A real optimizer run includes best_reward; the default plan doesn't
          const isOptimized = typeof data.best_reward === "number";
          if (isOptimized) setOptimizerRan(true);
          setPlan((prev) =>
            JSON.stringify(prev) === JSON.stringify(data) ? prev : data,
          );
        }
      } catch { /* keep map if API is down */ }
    };
    loadPlan();
    const timer = setInterval(loadPlan, 3000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [stateFips]);

  // ── EFFECT 1: Draw SVG structure once ────────────────────────────────────
  useEffect(() => {
    structureReadyRef.current = false;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    Promise.all([
      fetch("/us-states-10m.json").then((r) => r.json()),
      fetch("/counties-10m.json").then((r) => r.json()),
      fetch("/congressional-districts-10m.json").then((r) => r.json()),
    ]).then(([stateTopo, countyTopo, districtTopo]: [Topology, Topology, Topology]) => {
      const allStates = (
        topojson.feature(stateTopo, stateTopo.objects.states as GeometryCollection) as GeoJSON.FeatureCollection
      ).features;
      const stateFeature = allStates.find(
        (f) => String(f.id).padStart(2, "0") === stateFips,
      );
      if (!stateFeature) return;

      const projection = d3.geoMercator().fitSize([W - 40, H - 40], stateFeature);
      const path = d3.geoPath().projection(projection);
      const g = svg.append("g").attr("transform", "translate(20,20)");

      // ── State background ──────────────────────────────────────────────────
      g.append("path")
        .datum(stateFeature)
        .attr("d", path as never)
        .attr("fill", "#0f172a")
        .attr("stroke", "none");

      // ── County fills (optimizer layer — starts hidden) ────────────────────
      const allCounties = (
        topojson.feature(countyTopo, countyTopo.objects.counties as GeometryCollection) as GeoJSON.FeatureCollection
      ).features;
      const stateCounties = allCounties.filter((f) =>
        String(f.id).padStart(5, "0").startsWith(stateFips),
      );
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.county")
        .data(stateCounties)
        .join("path")
        .attr("class", "county")
        .attr("d", path as never)
        .attr("fill", "none")           // hidden until optimizer runs
        .attr("fill-opacity", 0.85)
        .attr("stroke", "none");

      // ── Real congressional district boundaries ────────────────────────────
      const allDistricts = (
        topojson.feature(districtTopo, districtTopo.objects.districts as GeometryCollection) as GeoJSON.FeatureCollection
      ).features;
      const stateDistricts = allDistricts.filter(
        (f) => (f.properties as Record<string, string>)?.STATEFP === stateFips,
      );

      // Assign a stable color per district number so the fill matches the legend
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.real-district")
        .data(stateDistricts)
        .join("path")
        .attr("class", "real-district")
        .attr("d", path as never)
        .attr("fill", (f) => {
          const cd = parseInt((f.properties as Record<string, string>)?.CD118FP ?? "1", 10);
          return districtColor(String(cd));
        })
        .attr("fill-opacity", 0.75)
        .attr("stroke", "rgba(255,255,255,0.35)")
        .attr("stroke-width", 0.6);

      // ── County grid lines (always on top of fills) ────────────────────────
      g.append("path")
        .datum(
          topojson.mesh(
            countyTopo,
            countyTopo.objects.counties as GeometryCollection,
            (a, b) =>
              a !== b &&
              String(a.id).padStart(5, "0").startsWith(stateFips) &&
              String(b.id).padStart(5, "0").startsWith(stateFips),
          ),
        )
        .attr("class", "county-mesh")
        .attr("fill", "none")
        .attr("stroke", "rgba(255,255,255,0.10)")
        .attr("stroke-width", 0.4)
        .attr("d", path as never);

      // ── Caption ───────────────────────────────────────────────────────────
      g.append("text")
        .attr("class", "caption")
        .attr("x", (W - 40) / 2)
        .attr("y", H - 55)
        .attr("text-anchor", "middle")
        .attr("font-size", 10)
        .attr("fill", "rgba(255,255,255,0.25)")
        .text("118th Congress · official boundaries");

      structureReadyRef.current = true;
      applyOptimizerColors(svg, planRef.current, districtColor, false);
    });
  }, [districtColor, stateFips]);

  // ── EFFECT 2: Update county colors when plan changes (no geometry removal) ─
  useEffect(() => {
    if (!structureReadyRef.current) return;
    applyOptimizerColors(d3.select(svgRef.current), plan, districtColor, optimizerRan);
  }, [plan, districtColor, optimizerRan]);

  // ── Legend ────────────────────────────────────────────────────────────────
  const legendItems = optimizerRan && plan?.district_metrics?.length
    ? plan.district_metrics.map((d) => ({
        label: `District ${d.district_id + 1}`,
        color: districtColor(String(d.district_id)),
        pop: d.population,
      }))
    : null;

  return (
    <div className="w-full rounded-xl border border-white/10 overflow-hidden bg-slate-900">
      <div className="px-4 py-2.5 border-b border-white/10 bg-slate-800/60 flex items-center justify-between">
        <span className="text-sm font-semibold text-white/90">{stateName} — District Map</span>
        <span className="text-xs text-white/35">
          {optimizerRan ? "Optimizer assignment (county-level)" : "118th Congress · official boundaries"}
        </span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        aria-label={`Map of ${stateName}`}
      />
      {legendItems ? (
        <div className="px-4 py-3 border-t border-white/10 flex flex-wrap gap-x-4 gap-y-1.5">
          {legendItems.map((item) => (
            <div key={item.label} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: item.color }}
              />
              <span className="text-[10px] text-white/50 font-mono">
                {item.label} · {item.pop.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="px-4 py-2.5 border-t border-white/10">
          <p className="text-[10px] text-white/25">
            Run the optimizer to see an AI-suggested county-level redistricting — colors will replace the official map above.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Pure D3 helper — updates county fills without touching geometry ──────────
function applyOptimizerColors(
  svg: d3.Selection<SVGSVGElement | null, unknown, null, undefined>,
  plan: DistrictPlan | null,
  districtColor: d3.ScaleOrdinal<string, string>,
  optimizerRan: boolean,
) {
  if (!optimizerRan || !plan) {
    // Show real district boundaries, hide county overlay
    svg.selectAll("path.real-district").attr("fill-opacity", 0.75).attr("stroke-opacity", 1);
    svg.selectAll("path.county").attr("fill", "none");
    svg.selectAll("text.caption").text("118th Congress · official boundaries");
    return;
  }

  // Hide real district boundaries, show county optimizer colors
  svg.selectAll("path.real-district").attr("fill-opacity", 0).attr("stroke-opacity", 0);
  svg.selectAll("path.county")
    .attr("fill", (f: GeoJSON.Feature) => {
      const countyId = String((f as GeoJSON.Feature).id).padStart(5, "0");
      const districtId = plan.assignment?.[countyId];
      return districtId === undefined ? "#1e293b" : districtColor(String(districtId));
    })
    .attr("stroke", "rgba(255,255,255,0.15)")
    .attr("stroke-width", 0.4);
  svg.selectAll("text.caption").text("Optimizer assignment · county-level approximation");
}
