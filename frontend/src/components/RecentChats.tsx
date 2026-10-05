"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { PlusIcon } from "./Icons";
import { useChats } from "@/lib/history";

/** "New chat" plus the visitor's recent conversations. The list lives in this browser only. */
export default function RecentChats({ onNavigate }: { onNavigate: () => void }) {
  const chats = useChats();
  const pathname = usePathname();
  const current = useSearchParams().get("c");

  return (
    <>
      <Link href="/chat?new=1" className="side-link new-chat" onClick={onNavigate}>
        <PlusIcon size={18} />
        New chat
      </Link>
      {chats.length > 0 && (
        <>
          <div className="side-label">Recent chats</div>
          <div className="recent">
            {chats.slice(0, 8).map((c) => {
              const active = pathname === "/chat" && current === c.id;
              return (
                <Link
                  key={c.id}
                  href={`/chat?c=${c.id}`}
                  className={`recent-link${active ? " active" : ""}`}
                  aria-current={active ? "page" : undefined}
                  title={c.title}
                  onClick={onNavigate}
                >
                  {c.title}
                </Link>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
