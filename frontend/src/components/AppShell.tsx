"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import Brand from "./Brand";
import { ChartIcon, ChatIcon, CloseIcon, FilesIcon, GithubIcon, HomeIcon, LockIcon, MenuIcon } from "./Icons";
import { REPO_URL } from "@/lib/site";
import { getSupabase } from "@/lib/supabase";

const MAIN = [
  { href: "/chat", label: "Ask the assistant", icon: ChatIcon },
  { href: "/evaluation", label: "Evaluation", icon: ChartIcon },
];
const ADMIN = [{ href: "/admin", label: "Documents", icon: FilesIcon }];

/** The app frame: a top bar, a side navbar, and the page. On phones the sidebar is a drawer. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const close = () => setOpen(false);

  // Customers should not see a back office they can't use. The Admin section appears only once
  // someone is signed in (sign-ups are disabled, so a signed-in user is an administrator).
  useEffect(() => {
    const supabase = getSupabase();
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_event, session) => setSignedIn(!!session));
    return () => data.subscription.unsubscribe();
  }, []);
  const showAdmin = signedIn || pathname === "/admin";

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const item = (l: { href: string; label: string; icon: typeof ChatIcon }) => {
    const active = pathname === l.href;
    const Icon = l.icon;
    return (
      <Link key={l.href} href={l.href} className={`side-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined} onClick={close}>
        <Icon size={18} />
        {l.label}
      </Link>
    );
  };

  return (
    <div className="app">
      <header className="topbar">
        <button className="menu-btn side-toggle" aria-label="Open navigation" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)}>
          <MenuIcon />
        </button>
        <Brand />
        <div className="topbar-spacer" />
        <Link href="/" className="top-link">
          Home
        </Link>
        <a className="icon-link" href={REPO_URL} target="_blank" rel="noopener noreferrer" aria-label="Source code on GitHub">
          <GithubIcon />
        </a>
      </header>

      <div className="app-body">
        {open && <div className="scrim" onClick={close} aria-hidden="true" />}
        <aside id="sidebar" className={`sidebar${open ? " open" : ""}`} aria-label="Sidebar">
          <button className="menu-btn side-close" aria-label="Close navigation" onClick={close}>
            <CloseIcon />
          </button>
          <nav aria-label="App">
            <div className="side-label">Assistant</div>
            {MAIN.map(item)}
            {showAdmin && (
              <>
                <div className="side-label">
                  <LockIcon size={12} /> Admin
                </div>
                {ADMIN.map(item)}
              </>
            )}
          </nav>
          <div className="side-foot">
            <Link href="/" className="side-link" onClick={close}>
              <HomeIcon size={18} />
              Back to home
            </Link>
            {!showAdmin && (
              <Link href="/admin" className="side-quiet" onClick={close}>
                Admin sign-in
              </Link>
            )}
          </div>
        </aside>
        <main className="app-main">
          <div key={pathname} className="page-enter">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
