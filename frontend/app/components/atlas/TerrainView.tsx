"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import type { Heightmap } from "../../../lib/api";
import { useWebGL } from "../../../lib/hooks";

const RAMPS: Record<string, [number, number, number][]> = {
  earth: [[0.20, 0.17, 0.13], [0.52, 0.42, 0.29], [0.80, 0.68, 0.48], [0.95, 0.90, 0.80]],
  mars: [[0.22, 0.12, 0.09], [0.52, 0.27, 0.17], [0.78, 0.46, 0.30], [0.93, 0.76, 0.60]],
};

function ramp(body: string, t: number): [number, number, number] {
  const stops = RAMPS[body] ?? RAMPS.earth;
  const x = Math.min(0.9999, Math.max(0, t)) * (stops.length - 1);
  const i = Math.floor(x), f = x - i;
  return [0, 1, 2].map((c) => stops[i][c] + (stops[i + 1][c] - stops[i][c]) * f) as [number, number, number];
}

function buildGeometry(map: Heightmap, exaggeration: number, sharedRange: [number, number]): THREE.BufferGeometry {
  const widthKm = (map.columns * map.resolution_m) / 1000;
  const heightKm = (map.rows * map.resolution_m) / 1000;
  const geometry = new THREE.PlaneGeometry(widthKm, heightKm, map.columns - 1, map.rows - 1);
  const positions = geometry.attributes.position as THREE.BufferAttribute;
  const colors = new Float32Array(positions.count * 3);
  const fill = map.relative_min_m;
  const [low, high] = sharedRange;
  for (let i = 0; i < positions.count; i += 1) {
    const raw = map.heights[i];
    const metres = raw === map.nodata ? fill : raw / 10;
    positions.setZ(i, (metres / 1000) * exaggeration);
    const [r, g, b] = ramp(map.body, (metres - low) / Math.max(1, high - low));
    colors.set([r, g, b], i * 3);
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function Surface({ map, exaggeration, offsetX, range }: { map: Heightmap; exaggeration: number; offsetX: number; range: [number, number] }) {
  const geometry = useMemo(() => buildGeometry(map, exaggeration, range), [map, exaggeration, range]);
  return (
    <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} position={[offsetX, 0, 0]}>
      <meshStandardMaterial vertexColors roughness={0.95} metalness={0} side={THREE.DoubleSide} />
    </mesh>
  );
}

export default function TerrainView({ maps, exaggeration, label }: { maps: Heightmap[]; exaggeration: number; label: string }) {
  const webgl = useWebGL();
  // One shared vertical range so side-by-side surfaces are drawn on the same metric scale.
  const range = useMemo<[number, number]>(() => [Math.min(...maps.map((m) => m.relative_min_m)), Math.max(...maps.map((m) => m.relative_max_m))], [maps]);
  if (webgl === null) return <div className="viewer-placeholder">Preparing terrain…</div>;
  if (!webgl) return <div className="viewer-placeholder">3D terrain needs WebGL, which is unavailable in this browser. The terrain evidence below is unaffected.</div>;
  const spacing = 11.2;
  const span = (maps.length - 1) * spacing;
  return (
    <div className="terrain-canvas" role="img" aria-label={label}>
      <Canvas camera={{ fov: 35, position: [0, 6 + maps.length * 2.5, 10 + maps.length * 4], near: 0.1, far: 200 }} dpr={[1, 1.75]} frameloop="demand">
        <color attach="background" args={["#0d1117"]} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[-8, 12, 6]} intensity={1.7} />
        {maps.map((map, index) => <Surface key={map.site_id} map={map} exaggeration={exaggeration} offsetX={index * spacing - span / 2} range={range} />)}
        <OrbitControls target={[0, 0, 0]} enablePan={false} minDistance={6} maxDistance={48} maxPolarAngle={Math.PI / 2.15} />
      </Canvas>
    </div>
  );
}
