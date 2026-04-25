"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import * as d3 from "d3";
import * as topojson from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";

// FIPS → state name + abbreviation
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

const WIDTH = 960;
const HEIGHT = 600;

export default function USMap() {
  const svgRef = useRef<SVGSVGElement>(null);
  const router = useRouter();
  const [tooltip, setTooltip] = useState<{ x: number; y: number; name: string } | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const projection = d3.geoAlbersUsa().scale(1300).translate([WIDTH / 2, HEIGHT / 2]);
    const pathGen = d3.geoPath().projection(projection);

    // Border mesh layer
    const g = svg.append("g");

    fetch("/us-states-10m.json")
      .then((r) => r.json())
      .then((topo: Topology) => {
        const states = topojson.feature(
          topo,
          topo.objects.states as GeometryCollection
        );

        // State fills
        g.selectAll<SVGPathElement, GeoJSON.Feature>("path.state")
          .data((states as GeoJSON.FeatureCollection).features)
          .join("path")
          .attr("class", "state")
          .attr("d", pathGen as never)
          .attr("fill", (d) => {
            const fips = String(d.id).padStart(2, "0");
            return hovered === fips ? "#4f86f7" : "#c8d8f0";
          })
          .attr("stroke", "#fff")
          .attr("stroke-width", 0.8)
          .style("cursor", "pointer")
          .on("mouseenter", function (event: MouseEvent, d) {
            const fips = String(d.id).padStart(2, "0");
            const info = FIPS_TO_STATE[fips];
            d3.select(this).attr("fill", "#4f86f7");
            setHovered(fips);
            setTooltip({ x: event.offsetX, y: event.offsetY, name: info?.name ?? fips });
          })
          .on("mousemove", function (event: MouseEvent) {
            setTooltip((t) => t ? { ...t, x: event.offsetX, y: event.offsetY } : null);
          })
          .on("mouseleave", function () {
            d3.select(this).attr("fill", "#c8d8f0");
            setHovered(null);
            setTooltip(null);
          })
          .on("click", (_event, d) => {
            const fips = String(d.id).padStart(2, "0");
            const info = FIPS_TO_STATE[fips];
            if (info) router.push(`/map/${info.abbr.toLowerCase()}`);
          });

        // State border mesh
        g.append("path")
          .datum(topojson.mesh(topo, topo.objects.states as GeometryCollection, (a, b) => a !== b))
          .attr("fill", "none")
          .attr("stroke", "#fff")
          .attr("stroke-width", 0.5)
          .attr("d", pathGen as never);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="relative w-full max-w-4xl">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto rounded-xl border border-border bg-slate-50"
        aria-label="Interactive US map — click a state to explore"
      />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 rounded-md bg-popover border border-border px-2.5 py-1 text-xs font-medium shadow-md text-popover-foreground"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          {tooltip.name}
        </div>
      )}
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Click any state to explore its redistricting simulation
      </p>
    </div>
  );
}
