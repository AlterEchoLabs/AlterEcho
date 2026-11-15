import type { Metadata } from "next";
import SourcesContent from "./SourcesContent";

export const metadata: Metadata = { title: "Data & sources · AlterEcho", description: "Every dataset, product, date and attribution behind AlterEcho." };

export default function SourcesPage() {
  return <SourcesContent />;
}
