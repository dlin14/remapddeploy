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

export default function StateMap({ stateFips, stateName }: StateMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [plan, setPlan] = useState<DistrictPlan | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadPlan = async () => {
      try {
        const resp = await fetch(`http://localhost:8000/api/states/${stateFips}/district-plan`, {
          cache: "no-store",
        });
        if (!resp.ok) return;
        const data = (await resp.json()) as DistrictPlan;
        if (!cancelled) setPlan(data);
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

  const districtColor = useMemo(() => d3.scaleOrdinal(d3.schemeTableau10), []);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const W = 700, H = 500;

    Promise.all([
      fetch("/us-states-10m.json").then((r) => r.json()),
      fetch("/counties-10m.json").then((r) => r.json()),
    ]).then(([stateTopo, countyTopo]: [Topology, Topology]) => {
      // Extract this state's GeoJSON feature
      const allStates = topojson.feature(
        stateTopo,
        stateTopo.objects.states as GeometryCollection
      ) as GeoJSON.FeatureCollection;

      const stateFeature = allStates.features.find(
        (f) => String(f.id).padStart(2, "0") === stateFips
      );
      if (!stateFeature) return;

      // Fit projection to this state's bounds
      const projection = d3.geoMercator().fitSize([W - 40, H - 40], stateFeature);
      const path = d3.geoPath().projection(projection);

      const g = svg.append("g").attr("transform", "translate(20,20)");

      // State fill
      g.append("path")
        .datum(stateFeature)
        .attr("d", path as never)
        .attr("fill", "#dbeafe")
        .attr("stroke", "#3b82f6")
        .attr("stroke-width", 1.5);

      // County borders within state (FIPS: county is 5-digit, starts with state 2-digit)
      const allCounties = topojson.feature(
        countyTopo,
        countyTopo.objects.counties as GeometryCollection
      ) as GeoJSON.FeatureCollection;

      const stateCounties = allCounties.features.filter((f) =>
        String(f.id).padStart(5, "0").startsWith(stateFips)
      );

      g.selectAll<SVGPathElement, GeoJSON.Feature>("path.county")
        .data(stateCounties)
        .join("path")
        .attr("class", "county")
        .attr("d", path as never)
        .attr("fill", (f) => {
          const countyId = String(f.id).padStart(5, "0");
          const districtId = plan?.assignment?.[countyId];
          return districtId === undefined ? "#e5e7eb" : districtColor(String(districtId));
        })
        .attr("fill-opacity", 0.9)
        .attr("stroke", "#6366f1")
        .attr("stroke-width", 0.4);

      // County mesh (internal borders only)
      const countyMesh = topojson.mesh(
        countyTopo,
        countyTopo.objects.counties as GeometryCollection,
        (a, b) =>
          a !== b &&
          String(a.id).padStart(5, "0").startsWith(stateFips) &&
          String(b.id).padStart(5, "0").startsWith(stateFips)
      );

      g.append("path")
        .datum(countyMesh)
        .attr("fill", "none")
        .attr("stroke", "#6366f1")
        .attr("stroke-width", 0.5)
        .attr("d", path as never);

      // Label
      g.append("text")
        .attr("x", (W - 40) / 2)
        .attr("y", H - 55)
        .attr("text-anchor", "middle")
        .attr("font-size", 11)
        .attr("fill", "#6b7280")
        .text("Counties colored by district assignment (latest optimizer run)");

      if (plan?.district_metrics?.length) {
        const legend = g.append("g").attr("transform", "translate(10,10)");
        plan.district_metrics.slice(0, 10).forEach((d, i) => {
          legend
            .append("rect")
            .attr("x", 0)
            .attr("y", i * 16)
            .attr("width", 10)
            .attr("height", 10)
            .attr("fill", districtColor(String(d.district_id)));
          legend
            .append("text")
            .attr("x", 14)
            .attr("y", i * 16 + 9)
            .attr("font-size", 10)
            .attr("fill", "#374151")
            .text(`D${d.district_id + 1} · pop ${d.population.toLocaleString()}`);
        });
      }
    });
  }, [districtColor, plan, stateFips]);

  return (
    <div className="w-full rounded-xl border border-border overflow-hidden bg-white">
      <div className="px-4 py-2 border-b border-border bg-muted/40 flex items-center justify-between">
        <span className="text-sm font-semibold">{stateName} — Geographic Overview</span>
        <span className="text-xs text-muted-foreground">County divisions · Click to select</span>
      </div>
      <svg
        ref={svgRef}
        viewBox="0 0 700 500"
        className="w-full h-auto"
        aria-label={`Map of ${stateName}`}
      />
    </div>
  );
}
