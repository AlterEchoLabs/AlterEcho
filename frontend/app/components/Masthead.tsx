"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { BRAND } from "../../config/brand";
import DetailToggle from "./DetailToggle";
import ThemeSelect from "./ThemeSelect";

const LINKS = [
  { href: "/", label: "Atlas" },
  { href: "/explore", label: "Explore an area" },
  { href: "/method", label: "Method" },
  { href: "/sources", label: "Data & sources" },
];

/** One fixed-height bar: compact logo lockup, the four destinations, and the reading-mode and theme controls.
 *  Below 960 px the links and controls fold into a menu so nothing is squeezed. */
export default function Masthead() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [openedOn, setOpenedOn] = useState(pathname);
  const menuId = useId();
  const button = useRef<HTMLButtonElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  // Following a link closes the menu (state reset during render, not in an effect).
  if (open && openedOn !== pathname) { setOpen(false); setOpenedOn(pathname); }

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); button.current?.focus(); } };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onPointer); };
  }, [open]);

  return (
    <header className="masthead" data-testid="masthead">
      <Link href="/" className="brand" aria-label={`${BRAND.shortName} home`}>
        <Image src="/alterecho-mark.png" alt="" width={168} height={96} priority className="brand-mark brand-mark-dark" />
        <Image src="/alterecho-mark-light.png" alt="" width={168} height={96} priority className="brand-mark brand-mark-light" />
        <span className="brand-word" aria-hidden="true"><span>Alter</span><span className="brand-echo">Echo</span></span>
      </Link>
      <button ref={button} type="button" className="menu-button" aria-expanded={open} aria-controls={menuId} data-testid="menu-button"
        onClick={() => { setOpen((v) => !v); setOpenedOn(pathname); }}>
        <span className="menu-icon" aria-hidden="true"><i /><i /><i /></span>
        <span>Menu</span>
      </button>
      <div ref={panel} id={menuId} className={`masthead-menu ${open ? "is-open" : ""}`} data-testid="masthead-menu">
        <nav aria-label="Primary">
          <ul className="masthead-nav">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link href={link.href} aria-current={pathname === link.href ? "page" : undefined} onClick={() => setOpen(false)}>{link.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="masthead-tools">
          <DetailToggle />
          <ThemeSelect />
        </div>
      </div>
    </header>
  );
}
