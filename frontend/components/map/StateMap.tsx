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
  assignment: Record<string, number>;
  district_metrics: Array<{
    district_id: number;
    num_counties: number;
    population: number;
    minority_share: number;
  }>;
}

const W = 700;
const H = 500;

export default function StateMap({ stateFips, stateName }: StateMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [plan, setPlan] = useState<DistrictPlan | null>(null);

  const districtColor = useMemo(() => d3.scaleOrdinal(d3.schemeTableau10), []);

  // Keep a ref so color-update effect always has fresh data
  const planRef = useRef<DistrictPlan | null>(null);
  const structureReadyRef = useRef(false);

  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  // ── Poll with deep-equal guard ────────────────────────────────────────────────
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
        if (!cancelled)
          setPlan((prev) =>
            JSON.stringify(prev) === JSON.stringify(data) ? prev : data,
          );
      } catch {
        // Keep static map if API is unavailable.
      }
    };
    loadPlan();
    const timer = setInterval(loadPlan, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [stateFips]);

  // ── EFFECT 1: Draw SVG geometry ONCE ─────────────────────────────────────────
  useEffect(() => {
    structureReadyRef.current = false;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    Promise.all([
      fetch("/us-states-10m.json").then((r) => r.json()),
      fetch("/counties-10m.json").then((r) => r.json()),
    ]).then(([stateTopo, countyTopo]: [Topology, Topology]) => {
      const allStates = topojson.feature(
        stateTopo,
        stateTopo.objects.states as GeometryCollection,
      ) as GeoJSON.FeatureCollection;

      const stateFeature = allStates.features.find(
        (f) => String(f.id).padStart(2, "0") === stateFips,
      );
      if (!stateFeature) return;

      const projection = d3.geoMercator().fitSize([W - 40, H - 40], stateFeature);
      const path = d3.geoPath().projection(projection);
      const g = svg.append("g").attr("transform", "translate(20,20)");

      // State background
      g.append("path")
        .datum(stateFeature)
        .attr("d", path as never)
        .attr("fill", "#0f172a")
        .attr("stroke", "rgba(99,102,241,0.4)")
        .attr("stroke-width", 1.5);

      const allCounties = topojson.feature(
        countyTopo,
        countyTopo.objects.counties as GeometryCollection,
      ) as GeoJSON.FeatureCollection;

      const stateCounties = allCounties.features.filter((f) =>
        String(f.id).padStart(5, "0").startsWith(stateFips),
      );

      // County fills (colored by district; starts grey)
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.county")
        .data(stateCounties)
        .join("path")
        .attr("class", "county")
        .attr("d", path as never)
        .attr("fill", "#1e293b")
        .attr("fill-opacity", 0.9)
        .attr("stroke", "rgba(99,102,241,0.25)")
        .attr("stroke-width", 0.4);

      // County internal mesh
      const countyMesh = topojson.mesh(
        countyTopo,
        countyTopo.objects.counties as GeometryCollection,
        (a, b) =>
          a !== b &&
          String(a.id).padStart(5, "0").startsWith(stateFips) &&
          String(b.id).padStart(5, "0").startsWith(stateFips),
      );
      g.append("path")
        .datum(countyMesh)
        .attr("fill", "none")
        .attr("stroke", "rgba(99,102,241,0.3)")
        .attr("stroke-width", 0.5)
        .attr("d", path as never);

      // Caption
      g.append("text")
        .attr("x", (W - 40) / 2)
        .attr("y", H - 55)
        .attr("text-anchor", "middle")
        .attr("font-size", 10)
        .attr("fill", "rgba(255,255,255,0.25)")
        .text("Counties shaded by congressional district assignment");

      structureReadyRef.current = true;
      // Apply whatever plan was already loaded
      applyCountyColors(svg, planRef.current, districtColor);
    });
  }, [districtColor, stateFips]); // ← excludes `plan`

  // ── EFFECT 2: Update county fill colors only — no geometry removal ────────────
  useEffect(() => {
    if (!structureReadyRef.current) return;
    applyCountyColors(d3.select(svgRef.current), plan, districtColor);
  }, [plan, districtColor]);

  return (
    <div className="w-full rounded-xl border border-white/10 overflow-hidden bg-slate-900">
      <div className="px-4 py-2.5 border-b border-white/10 bg-slate-800/60 flex items-center justify-between">
        <span className="text-sm font-semibold text-white/90">{stateName} — District Map</span>
        <span className="text-xs text-white/35">County divisions · optimizer assigns colors</span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        aria-label={`Map of ${stateName}`}
      />
      {plan?.district_metrics?.length ? (
        <div className="px-4 py-3 border-t border-white/10 flex flex-wrap gap-x-4 gap-y-1.5">
          {plan.district_metrics.map((d) => (
            <div key={d.district_id} className="flex items-center gap-1.5">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: districtColor(String(d.district_id)) }}
              />
              <span className="text-[10px] text-white/50 font-mono">
                District {d.district_id + 1} · {d.population.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function applyCountyColors(
  svg: d3.Selection<SVGSVGElement | null, unknown, null, undefined>,
  plan: DistrictPlan | null,
  districtColor: d3.ScaleOrdinal<string, string>,
) {
  svg.selectAll<SVGPathElement, GeoJSON.Feature>("path.county").attr("fill", (f) => {
    const countyId = String(f.id).padStart(5, "0");
    const districtId = plan?.assignment?.[countyId];
    return districtId === undefined ? "#1e293b" : districtColor(String(districtId));
  });
}
