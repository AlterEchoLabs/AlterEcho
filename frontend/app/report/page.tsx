import type { Metadata } from "next";
import ReportContent from "./ReportContent";

export const metadata: Metadata = { title: "Comparison report · AlterEcho", description: "A reproducible record of one AlterEcho comparison." };

export default function ReportPage() {
  return <ReportContent />;
}
