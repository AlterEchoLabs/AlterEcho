"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { BRAND } from "../../config/brand";
import DetailToggle from "./DetailToggle";
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
        <Image
          src="/alterecho-header-logo.png"
          alt="AlterEcho"
          width={1028}
          height={768}
          priority
          className="wordmark-logo"
        />
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
      <div className="masthead-tools">
        <DetailToggle />
        <ThemeSelect />
      </div>
    </header>
  );
}
