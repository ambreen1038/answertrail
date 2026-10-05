"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, Suspense, useEffect, useState } from "react";
import { useAccount } from "./AccountProvider";
import Brand from "./Brand";
import { ChartIcon, ChatIcon, CloseIcon, FilesIcon, HomeIcon, InsightIcon, LockIcon, MenuIcon, UserIcon } from "./Icons";
import RecentChats from "./RecentChats";
import { apiFetch } from "@/lib/api";
import { setServerChats } from "@/lib/history";
import { getSupabase } from "@/lib/supabase";

const MAIN = [
  { href: "/chat", label: "Ask the assistant", icon: ChatIcon },
  { href: "/evaluation", label: "Evaluation", icon: ChartIcon },
];
const ADMIN = [
  { href: "/admin", label: "Documents", icon: FilesIcon },
  { href: "/admin/analytics", label: "Analytics", icon: InsightIcon },
];

/** The app frame: a top bar, a side navbar, and the page. On phones the sidebar is a drawer. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const account = useAccount();
  const close = () => setOpen(false);

  // Customers should not see a back office they can't use. The Admin section appears only when the
  // SERVER says this account is an administrator (being signed in is not enough: anyone can sign up).
  const showAdmin = account.isAdmin;

  async function signOut() {
    close();
    await getSupabase()?.auth.signOut();
    router.push("/chat?new=1");
  }

  async function deleteAllChats() {
    if (!window.confirm("Delete all of your chats? Their questions and answers will be removed permanently.")) return;
    close();
    try {
      const res = await apiFetch("/api/me/conversations", { method: "DELETE" });
      if (!res.ok) throw new Error();
      setServerChats([]);
      router.push("/chat?new=1");
    } catch {
      window.alert("Couldn't delete your chats. Please try again.");
    }
  }

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
            <Suspense fallback={null}>
              <RecentChats onNavigate={close} />
            </Suspense>
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
            {account.signedIn ? (
              <div className="account">
                <div className="account-name" title={account.name ?? account.email ?? undefined}>
                  {account.name ?? account.email}
                </div>
                {account.name && (
                  <div className="account-email" title={account.email ?? undefined}>
                    {account.email}
                  </div>
                )}
                <button className="link" onClick={() => void signOut()}>
                  Sign out
                </button>
                <button className="link subtle" onClick={() => void deleteAllChats()}>
                  Delete all my chats
                </button>
              </div>
            ) : (
              <Link href="/login" className="side-link" onClick={close}>
                <UserIcon size={18} />
                Sign in
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
