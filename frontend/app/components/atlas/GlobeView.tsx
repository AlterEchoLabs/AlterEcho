"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, useTexture } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useWebGL } from "../../../lib/hooks";
import type { Body } from "../../../lib/api";

export const GLOBE_TEXTURES: Record<Body, { src: string; credit: string; note: string }> = {
  earth: { src: "/textures/earth-blue-marble-4k.jpg", credit: "NASA Blue Marble: Next Generation (via NASA GIBS)", note: "2004 cloud-free composite" },
  mars: { src: "/textures/mars-viking-mdim-4k.jpg", credit: "USGS Astrogeology Viking colour mosaic, 925 m", note: "Viking-era global mosaic" },
  moon: { src: "/textures/moon-lroc-wac-2k.jpg", credit: "NASA SVS CGI Moon Kit, LRO LROC WAC", note: "LRO colour map" },
};

/** three.js SphereGeometry places u=0 at longitude −180°, matching equirectangular mosaics centred on 0°. */
function toVector(latitude: number, longitude: number, radius = 1): THREE.Vector3 {
  const phi = ((longitude + 180) / 360) * Math.PI * 2;
  const theta = ((90 - latitude) / 180) * Math.PI;
  return new THREE.Vector3(-Math.cos(phi) * Math.sin(theta) * radius, Math.cos(theta) * radius, Math.sin(phi) * Math.sin(theta) * radius);
}

function Planet({ body }: { body: Body }) {
  const texture = useTexture(GLOBE_TEXTURES[body].src, (loaded) => {
    const list = Array.isArray(loaded) ? loaded : [loaded];
    for (const item of list) { item.colorSpace = THREE.SRGBColorSpace; item.anisotropy = 4; }
  });
  return (
    <mesh>
      <sphereGeometry args={[1, 128, 96]} />
      <meshStandardMaterial map={texture} roughness={1} metalness={0} />
    </mesh>
  );
}

function Marker({ latitude, longitude, color }: { latitude: number; longitude: number; color: string }) {
  const position = useMemo(() => toVector(latitude, longitude, 1.004), [latitude, longitude]);
  const quaternion = useMemo(() => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), position.clone().normalize()), [position]);
  return (
    <group position={position} quaternion={quaternion}>
      <mesh><ringGeometry args={[0.022, 0.034, 48]} /><meshBasicMaterial color={color} side={THREE.DoubleSide} /></mesh>
      <mesh><circleGeometry args={[0.009, 24]} /><meshBasicMaterial color={color} /></mesh>
    </group>
  );
}

const CAMERA_DISTANCE = 4.1;

function FaceSite({ latitude, longitude }: { latitude: number; longitude: number }) {
  const { camera, invalidate } = useThree();
  useEffect(() => {
    // Polar sites: view from 70° so the camera never aligns with its up vector.
    camera.position.copy(toVector(Math.max(-70, Math.min(70, latitude)), longitude, CAMERA_DISTANCE));
    camera.lookAt(0, 0, 0);
    invalidate();
  }, [camera, invalidate, latitude, longitude]);
  return null;
}

/** Key light follows the viewer (slightly up and to the left) so the facing hemisphere is lit wherever the site is. */
function ViewerLight() {
  const light = useRef<THREE.DirectionalLight>(null);
  const { camera } = useThree();
  const offset = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    if (!light.current) return;
    offset.set(-1.2, 1.0, 0).applyQuaternion(camera.quaternion);
    light.current.position.copy(camera.position).add(offset);
  });
  return <directionalLight ref={light} intensity={1.9} />;
}

export function FlatFallback({ body, latitude, longitude, label }: { body: Body; latitude?: number; longitude?: number; label: string }) {
  return (
    <div className="globe-fallback" role="img" aria-label={label}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={GLOBE_TEXTURES[body].src} alt="" loading="lazy" />
      {latitude != null && longitude != null && <span className="globe-fallback-pin" style={{ left: `${((longitude + 180) / 360) * 100}%`, top: `${((90 - latitude) / 180) * 100}%` }} />}
      <p className="globe-fallback-note">3D globe unavailable (WebGL is off). Showing the flat global mosaic.</p>
    </div>
  );
}

export default function GlobeView({ body, latitude, longitude, label, markerColor = "#e3c178" }: {
  body: Body; latitude?: number; longitude?: number; label: string; markerColor?: string;
}) {
  const webgl = useWebGL();
  if (webgl === null) return <div className="viewer-placeholder">Preparing globe…</div>;
  if (!webgl) return <FlatFallback body={body} latitude={latitude} longitude={longitude} label={label} />;
  return (
    <div className="globe-canvas" role="img" aria-label={label}>
      <Canvas camera={{ fov: 32, near: 0.1, far: 50, position: [0, 0, CAMERA_DISTANCE] }} dpr={[1, 1.75]} gl={{ antialias: true, alpha: true }} frameloop="demand">
        <ambientLight intensity={0.35} />
        <ViewerLight />
        <Suspense fallback={null}>
          <Planet body={body} />
          {latitude != null && longitude != null && <Marker latitude={latitude} longitude={longitude} color={markerColor} />}
        </Suspense>
        {latitude != null && longitude != null && <FaceSite latitude={latitude} longitude={longitude} />}
        <OrbitControls enablePan={false} minDistance={1.7} maxDistance={6} rotateSpeed={0.5} zoomSpeed={0.6} enableDamping={false} autoRotate={false} />
      </Canvas>
    </div>
  );
}
