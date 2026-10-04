"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Brand from "./Brand";
import { CloseIcon, GithubIcon, MenuIcon } from "./Icons";
import { REPO_URL } from "@/lib/site";

const LINKS = [
  { href: "/#how", label: "How it works" },
  { href: "/#features", label: "Features" },
  { href: "/#proof", label: "Results" },
  { href: "/evaluation", label: "Evaluation" },
];

/** Top navigation for the landing page. On small screens the links fold into a menu. */
export default function MarketingNav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const close = () => setOpen(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`mnav${scrolled ? " scrolled" : ""}`}>
      <div className="mnav-inner">
        <Brand />
        <nav className="mnav-links" aria-label="Main">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="mnav-actions">
          <a className="icon-link" href={REPO_URL} target="_blank" rel="noopener noreferrer" aria-label="Source code on GitHub">
            <GithubIcon />
          </a>
          <Link href="/chat" className="btn btn-primary btn-sm">
            Try the demo
          </Link>
          <button
            className="menu-btn"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="mnav-menu"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>
      {open && (
        <nav id="mnav-menu" className="mnav-menu" aria-label="Mobile">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} onClick={close}>
              {l.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
