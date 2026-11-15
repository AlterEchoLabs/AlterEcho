"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BRAND } from "../../config/brand";
import ThemeSelect from "./ThemeSelect";

const LINKS = [
  { href: "/", label: "Atlas" },
  { href: "/explore", label: "Explore an area" },
  { href: "/method", label: "Method" },
  { href: "/sources", label: "Data & sources" },
];

export default function Masthead() {
  const pathname = usePathname();
  return (
    <header className="masthead">
      <Link href="/" className="wordmark" aria-label={`${BRAND.shortName} home`}>
        <svg viewBox="0 0 28 28" aria-hidden="true" className="wordmark-mark">
          <circle cx="11" cy="14" r="7.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <circle cx="20.5" cy="9" r="3.2" fill="currentColor" opacity=".55" />
        </svg>
        <span className="wordmark-name">{BRAND.shortName}</span>
        <span className="wordmark-team">{BRAND.teamName}</span>
      </Link>
      <nav aria-label="Primary">
        <ul className="masthead-nav">
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} aria-current={pathname === link.href ? "page" : undefined}>{link.label}</Link>
            </li>
          ))}
        </ul>
      </nav>
      <ThemeSelect />
    </header>
  );
}
