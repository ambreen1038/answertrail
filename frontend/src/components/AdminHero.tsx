"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccount } from "./AccountProvider";
import { ChatIcon, FilesIcon, InsightIcon } from "./Icons";
import PageHero from "./PageHero";

const TABS = [
  { href: "/admin", label: "Documents", icon: FilesIcon },
  { href: "/admin/analytics", label: "Analytics", icon: InsightIcon },
];

/** The banner at the top of every admin page: a greeting, what this page is for, and tabs to move
 *  between the admin pages. Purely presentational; access is decided by the server. */
export default function AdminHero({ title, subtitle }: { title: string; subtitle: string }) {
  const pathname = usePathname();
  const { name } = useAccount();
  const first = name?.trim().split(/\s+/)[0];

  return (
    <PageHero eyebrow={first ? `Welcome back, ${first}` : "Admin"} title={title} subtitle={subtitle}>
      <nav className="dash-tabs" aria-label="Admin pages">
        {TABS.map((t) => {
          const active = pathname === t.href;
          return (
            <Link key={t.href} href={t.href} className={`dash-tab${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
              <t.icon size={16} />
              {t.label}
            </Link>
          );
        })}
        <Link href="/chat" className="dash-tab ghost">
          <ChatIcon size={16} />
          Open chat
        </Link>
      </nav>
    </PageHero>
  );
}
