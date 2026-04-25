"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";
import * as topojson from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";

interface StateMapProps {
  stateFips: string;
  stateName: string;
}

export default function StateMap({ stateFips, stateName }: StateMapProps) {
  const svgRef = useRef<SVGSVGElement>(null);

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
        .attr("fill", "none")
        .attr("stroke", "#6366f1")
        .attr("stroke-width", 0.6)
        .attr("stroke-dasharray", "2,2");

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
        .text("County boundaries shown — congressional district overlay coming soon");
    });
  }, [stateFips]);

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
