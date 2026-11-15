import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import "./phase8.css";
import "./phase9.css";
import "./phase10.css";
import "katex/dist/katex.min.css";
import "./release.css";
import "./polish.css";
import Link from "next/link";
import { BRAND } from "../config/brand";
import Masthead from "./components/Masthead";

const serif = Newsreader({ variable: "--font-serif", subsets: ["latin"], weight: ["400", "500", "600"], style: ["normal", "italic"], display: "swap" });
const sans = IBM_Plex_Sans({ variable: "--font-sans", subsets: ["latin"], weight: ["400", "500", "600"], display: "swap" });
const mono = IBM_Plex_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["400", "500"], display: "swap" });

export const metadata: Metadata = {
  title: `${BRAND.shortName} · Earth analogs for Jezero Crater`,
  description: BRAND.description,
  icons: { icon: "/alterecho-favicon.png" },
};

export const viewport: Viewport = { colorScheme: "dark light" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <head><script dangerouslySetInnerHTML={{ __html: `(function(){var r=document.documentElement,m=matchMedia('(prefers-color-scheme: dark)'),p='system';try{p=localStorage.getItem('alterecho-theme')||p}catch(e){}if(!['dark','light','system'].includes(p))p='system';r.dataset.preference=p;function apply(){r.dataset.theme=r.dataset.preference==='system'?(m.matches?'dark':'light'):r.dataset.preference}apply();m.addEventListener('change',apply)})();` }} /></head>
      <body data-application-id={BRAND.applicationId} data-build-identifier={BRAND.buildIdentifier}>
        <a className="skip-link" href="#main">Skip to content</a>
        <Masthead />
        <main id="main" tabIndex={-1}>{children}</main>
        <footer className="site-footer" data-testid="site-footer">
          <div className="footer-inner">
            <p className="footer-brand"><strong>{BRAND.shortName}</strong> · Earth terrain compared with Mars and the Moon, from real elevation data.</p>
            <div className="footer-team">
              <h2 className="footer-heading">Team members</h2>
              <ul className="team-list" data-testid="team-members">
                {BRAND.teamMembers.map((name) => <li key={name}>{name}</li>)}
              </ul>
            </div>
            <p className="footer-note">Every score is calculated from stored measurements. <Link href="/method">How it works</Link> · <Link href="/sources">Data &amp; sources</Link></p>
          </div>
        </footer>
      </body>
    </html>
  );
}
