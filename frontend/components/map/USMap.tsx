"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import * as d3 from "d3";
import * as topojson from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";

const FIPS_TO_STATE: Record<string, { name: string; abbr: string }> = {
  "01": { name: "Alabama", abbr: "AL" },
  "02": { name: "Alaska", abbr: "AK" },
  "04": { name: "Arizona", abbr: "AZ" },
  "05": { name: "Arkansas", abbr: "AR" },
  "06": { name: "California", abbr: "CA" },
  "08": { name: "Colorado", abbr: "CO" },
  "09": { name: "Connecticut", abbr: "CT" },
  "10": { name: "Delaware", abbr: "DE" },
  "11": { name: "District of Columbia", abbr: "DC" },
  "12": { name: "Florida", abbr: "FL" },
  "13": { name: "Georgia", abbr: "GA" },
  "15": { name: "Hawaii", abbr: "HI" },
  "16": { name: "Idaho", abbr: "ID" },
  "17": { name: "Illinois", abbr: "IL" },
  "18": { name: "Indiana", abbr: "IN" },
  "19": { name: "Iowa", abbr: "IA" },
  "20": { name: "Kansas", abbr: "KS" },
  "21": { name: "Kentucky", abbr: "KY" },
  "22": { name: "Louisiana", abbr: "LA" },
  "23": { name: "Maine", abbr: "ME" },
  "24": { name: "Maryland", abbr: "MD" },
  "25": { name: "Massachusetts", abbr: "MA" },
  "26": { name: "Michigan", abbr: "MI" },
  "27": { name: "Minnesota", abbr: "MN" },
  "28": { name: "Mississippi", abbr: "MS" },
  "29": { name: "Missouri", abbr: "MO" },
  "30": { name: "Montana", abbr: "MT" },
  "31": { name: "Nebraska", abbr: "NE" },
  "32": { name: "Nevada", abbr: "NV" },
  "33": { name: "New Hampshire", abbr: "NH" },
  "34": { name: "New Jersey", abbr: "NJ" },
  "35": { name: "New Mexico", abbr: "NM" },
  "36": { name: "New York", abbr: "NY" },
  "37": { name: "North Carolina", abbr: "NC" },
  "38": { name: "North Dakota", abbr: "ND" },
  "39": { name: "Ohio", abbr: "OH" },
  "40": { name: "Oklahoma", abbr: "OK" },
  "41": { name: "Oregon", abbr: "OR" },
  "42": { name: "Pennsylvania", abbr: "PA" },
  "44": { name: "Rhode Island", abbr: "RI" },
  "45": { name: "South Carolina", abbr: "SC" },
  "46": { name: "South Dakota", abbr: "SD" },
  "47": { name: "Tennessee", abbr: "TN" },
  "48": { name: "Texas", abbr: "TX" },
  "49": { name: "Utah", abbr: "UT" },
  "50": { name: "Vermont", abbr: "VT" },
  "51": { name: "Virginia", abbr: "VA" },
  "53": { name: "Washington", abbr: "WA" },
  "54": { name: "West Virginia", abbr: "WV" },
  "55": { name: "Wisconsin", abbr: "WI" },
  "56": { name: "Wyoming", abbr: "WY" },
};

interface DistrictPlan {
  state_fips: string;
  assignment: Record<string, number>;
}

const WIDTH = 960;
const HEIGHT = 600;
const POLL_MS = 3500;
const DEFAULT_FILL = "#1e3461";
const HOVER_FILL = "#4f46e5";

/** Pure D3 helper — updates only fill/stroke attrs, never touches geometry. No flicker. */
function applyPlanColors(
  svg: d3.Selection<SVGSVGElement | null, unknown, null, undefined>,
  plans: Record<string, DistrictPlan>,
  districtColor: d3.ScaleOrdinal<string, string>,
) {
  const optimizedFips = new Set(Object.values(plans).map((p) => p.state_fips));
  const countyDistrict: Record<string, number> = {};
  for (const plan of Object.values(plans)) {
    for (const [fips, distId] of Object.entries(plan.assignment)) {
      countyDistrict[fips] = distId;
    }
  }

  svg
    .selectAll<SVGPathElement, GeoJSON.Feature>("path.state-fill")
    .attr("fill", (d) =>
      optimizedFips.has(String(d.id).padStart(2, "0")) ? "none" : DEFAULT_FILL,
    );

  svg
    .selectAll<SVGPathElement, GeoJSON.Feature>("path.county-fill")
    .attr("fill", (d) => {
      const countyFips = String(d.id).padStart(5, "0");
      const stateFips = countyFips.slice(0, 2);
      if (!optimizedFips.has(stateFips)) return "none";
      const distId = countyDistrict[countyFips];
      return distId !== undefined ? districtColor(String(distId)) : "#374151";
    })
    .attr("stroke", (d) => {
      const stateFips = String(d.id).padStart(5, "0").slice(0, 2);
      return optimizedFips.has(stateFips) ? "rgba(255,255,255,0.35)" : "none";
    });
}

export default function USMap() {
  const svgRef = useRef<SVGSVGElement>(null);
  const router = useRouter();
  const [tooltip, setTooltip] = useState<{ x: number; y: number; label: string } | null>(null);
  const [plans, setPlans] = useState<Record<string, DistrictPlan>>({});

  const districtColor = useMemo(() => d3.scaleOrdinal(d3.schemeTableau10), []);

  // Keep a ref so hover handlers always see fresh plans without triggering redraws
  const plansRef = useRef<Record<string, DistrictPlan>>({});
  const structureReadyRef = useRef(false);

  useEffect(() => {
    plansRef.current = plans;
  }, [plans]);

  // ── Poll with deep-equal guard (prevents needless re-renders when data hasn't changed) ──
  useEffect(() => {
    const load = () =>
      fetch("http://localhost:8000/api/agent/all-plans", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          if (data)
            setPlans((prev) =>
              JSON.stringify(prev) === JSON.stringify(data) ? prev : data,
            );
        })
        .catch(() => {});
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, []);

  // ── EFFECT 1: Draw SVG geometry ONCE. Never re-runs on plan changes. ──────────
  useEffect(() => {
    structureReadyRef.current = false;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const projection = d3.geoAlbersUsa().scale(1300).translate([WIDTH / 2, HEIGHT / 2]);
    const path = d3.geoPath().projection(projection);
    const g = svg.append("g");

    Promise.all([
      fetch("/us-states-10m.json").then((r) => r.json()),
      fetch("/counties-10m.json").then((r) => r.json()),
    ]).then(([stateTopo, countyTopo]: [Topology, Topology]) => {
      const stateFeatures = (
        topojson.feature(
          stateTopo,
          stateTopo.objects.states as GeometryCollection,
        ) as GeoJSON.FeatureCollection
      ).features;

      const countyFeatures = (
        topojson.feature(
          countyTopo,
          countyTopo.objects.counties as GeometryCollection,
        ) as GeoJSON.FeatureCollection
      ).features;

      // Layer 1 — state base fills (default navy; "none" for optimized states)
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.state-fill")
        .data(stateFeatures)
        .join("path")
        .attr("class", "state-fill")
        .attr("d", path as never)
        .attr("fill", DEFAULT_FILL)
        .attr("stroke", "none");

      // Layer 2 — county fills (starts invisible; applyPlanColors sets colors)
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.county-fill")
        .data(countyFeatures)
        .join("path")
        .attr("class", "county-fill")
        .attr("d", path as never)
        .attr("fill", "none")
        .attr("stroke", "none")
        .attr("stroke-width", 0.3)
        .attr("pointer-events", "none");

      // Layer 3 — invisible hit areas for hover + click
      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.state-hit")
        .data(stateFeatures)
        .join("path")
        .attr("class", "state-hit")
        .attr("d", path as never)
        .attr("fill", "transparent")
        .attr("stroke", "none")
        .style("cursor", "pointer")
        .on("mouseenter", function (event: MouseEvent, d) {
          const fips = String(d.id).padStart(2, "0");
          const info = FIPS_TO_STATE[fips];
          const isOptimized = new Set(
            Object.values(plansRef.current).map((p) => p.state_fips),
          ).has(fips);
          const label = info
            ? `${info.name}${isOptimized ? " ✓ optimized" : ""}`
            : fips;
          setTooltip({ x: event.offsetX, y: event.offsetY, label });
          if (!isOptimized) {
            svg
              .selectAll<SVGPathElement, GeoJSON.Feature>("path.state-fill")
              .filter((fd) => String(fd.id).padStart(2, "0") === fips)
              .attr("fill", HOVER_FILL);
          }
        })
        .on("mousemove", (event: MouseEvent) => {
          setTooltip((t) => (t ? { ...t, x: event.offsetX, y: event.offsetY } : null));
        })
        .on("mouseleave", function (_event, d) {
          const fips = String(d.id).padStart(2, "0");
          setTooltip(null);
          const isOptimized = new Set(
            Object.values(plansRef.current).map((p) => p.state_fips),
          ).has(fips);
          if (!isOptimized) {
            svg
              .selectAll<SVGPathElement, GeoJSON.Feature>("path.state-fill")
              .filter((fd) => String(fd.id).padStart(2, "0") === fips)
              .attr("fill", DEFAULT_FILL);
          }
        })
        .on("click", (_event, d) => {
          const fips = String(d.id).padStart(2, "0");
          const info = FIPS_TO_STATE[fips];
          if (info) router.push(`/map/${info.abbr.toLowerCase()}`);
        });

      // Layer 4 — state border mesh (always on top)
      g.append("path")
        .datum(
          topojson.mesh(
            stateTopo,
            stateTopo.objects.states as GeometryCollection,
            (a, b) => a !== b,
          ),
        )
        .attr("fill", "none")
        .attr("stroke", "rgba(255,255,255,0.18)")
        .attr("stroke-width", 0.7)
        .attr("pointer-events", "none")
        .attr("d", path as never);

      structureReadyRef.current = true;
      // Apply whatever plans were already loaded before geometry finished
      applyPlanColors(svg, plansRef.current, districtColor);
    });
  }, [districtColor, router]); // ← deliberately excludes `plans`

  // ── EFFECT 2: Update colors only — no geometry removal, no flicker ────────────
  useEffect(() => {
    if (!structureReadyRef.current) return;
    applyPlanColors(d3.select(svgRef.current), plans, districtColor);
  }, [plans, districtColor]);

  const optimizedCount = Object.keys(plans).length;

  return (
    <div className="relative w-full max-w-5xl">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto rounded-2xl border border-white/10 bg-slate-900/60"
        aria-label="Interactive US map — click a state to explore"
      />

      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 rounded-md bg-slate-800 border border-white/15 px-2.5 py-1 text-xs font-medium shadow-lg text-white/90"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          {tooltip.label}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between px-1">
        <p className="text-xs text-white/35">
          Click any state to explore · run the optimizer to see district colors
        </p>
        {optimizedCount > 0 && (
          <p className="text-xs font-medium text-indigo-400">
            {optimizedCount} state{optimizedCount > 1 ? "s" : ""} optimized
          </p>
        )}
      </div>
    </div>
  );
}
