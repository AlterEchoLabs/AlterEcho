
"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls, useGLTF } from "@react-three/drei";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Site } from "../../lib/api";

const DEFAULT_MARS_REFERENCE = { name: "Jezero Crater", latitude: 18.38, longitude: 77.58 };
const MARS_PRIME_MERIDIAN_LOCAL_DEGREES = 134.64;

function marsLocationPosition(latitude: number, longitude: number) {
  const latitudeRadians = THREE.MathUtils.degToRad(latitude);
  const localLongitudeRadians = THREE.MathUtils.degToRad(MARS_PRIME_MERIDIAN_LOCAL_DEGREES - longitude);
  const radius = 1.77;

  return new THREE.Vector3(
    radius * Math.cos(latitudeRadians) * Math.cos(localLongitudeRadians),
    radius * Math.sin(latitudeRadians),
    radius * Math.cos(latitudeRadians) * Math.sin(localLongitudeRadians),
  );
}

function MoonModel() {
  const moonRef = useRef<THREE.Group>(null);

  const { scene } = useGLTF("/models/moon.glb");

  // Clone and normalize the NASA model
  const moon = useMemo(() => {
    const model = scene.clone(true);

    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());

    model.position.sub(center);

    const maxDimension = Math.max(size.x, size.y, size.z);

    if (maxDimension > 0) {
      model.scale.setScalar(3.5 / maxDimension);
    }

    return model;
  }, [scene]);

  useFrame((_, delta) => {
    if (moonRef.current) {
      moonRef.current.rotation.y += delta * 0.025;
    }
  });

  return (
    <group ref={moonRef}>
      <primitive object={moon} />
    </group>
  );
}

function MarsModel({ site = DEFAULT_MARS_REFERENCE }: { site?: Pick<Site, "name" | "latitude" | "longitude"> }) {
  const planetRef = useRef<THREE.Group>(null);
  const { scene } = useGLTF("/models/Mars.glb");

  const mars = useMemo(() => {
    const model = scene.clone(true);
    const bounds = new THREE.Box3().setFromObject(model);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z);

    model.position.sub(center);

    if (maxDimension > 0) {
      model.scale.setScalar(3.5 / maxDimension);
    }

    return model;
  }, [scene]);
  const jezeroPosition = useMemo(() => marsLocationPosition(site.latitude, site.longitude), [site.latitude, site.longitude]);

  useFrame((_, delta) => {
    if (planetRef.current) {
      planetRef.current.rotation.y += delta * 0.08;
    }
  });

  return (
    <group ref={planetRef}>
      <primitive object={mars} />
      <Html position={jezeroPosition} occlude>
        <div className="mars-location-marker" data-testid="mars-location-marker" role="img" aria-label={`${site.name} approximate location`}>
          {site.name}
        </div>
      </Html>
    </group>
  );
}

export default function PlanetViewer({
  planet,
  site,
}: {
  planet: "mars" | "moon";
  site?: Pick<Site, "name" | "latitude" | "longitude"> | null;
}) {
  return (
    <div style={{ width: "100%", height: "650px" }}>
      <Canvas
        camera={{ position: [0, 0, 7], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
      >
        <ambientLight intensity={0.8} />

        <directionalLight
          position={[4, 3, 5]}
          intensity={2}
        />

        <pointLight
          position={[-4, -2, -3]}
          intensity={0.5}
          color="#8bbcff"
        />

        {planet === "moon" ? (
          <MoonModel />
        ) : (
          <MarsModel site={site ?? DEFAULT_MARS_REFERENCE} />
        )}

        <OrbitControls
          enablePan={false}
          enableZoom={true}
          minDistance={3}
          maxDistance={12}
          rotateSpeed={0.8}
        />
      </Canvas>
    </div>
  );
}

useGLTF.preload("/models/moon.glb");
useGLTF.preload("/models/Mars.glb");
