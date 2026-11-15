import type { Metadata } from "next";
import ExploreContent from "./ExploreContent";

export const metadata: Metadata = { title: "Explore an area · TerraLuna", description: "Screen a new 10 km Earth study window against the processed planetary references." };

export default function ExplorePage() {
  return <ExploreContent />;
}
