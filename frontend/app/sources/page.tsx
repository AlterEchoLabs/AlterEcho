import type { Metadata } from "next";
import SourcesContent from "./SourcesContent";

export const metadata: Metadata = { title: "Data & sources · TerraLuna", description: "Every dataset, product, date and attribution behind TerraLuna." };

export default function SourcesPage() {
  return <SourcesContent />;
}
