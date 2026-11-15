import type { Metadata } from "next";
import MethodContent from "./MethodContent";

export const metadata: Metadata = { title: "Method · TerraLuna", description: "How TerraLuna measures, compares and limits its Earth–Mars analog evidence." };

export default function MethodPage() {
  return <MethodContent />;
}
