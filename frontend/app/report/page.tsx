import type { Metadata } from "next";
import ReportContent from "./ReportContent";

export const metadata: Metadata = { title: "Comparison report · TerraLuna", description: "A reproducible record of one TerraLuna comparison." };

export default function ReportPage() {
  return <ReportContent />;
}
