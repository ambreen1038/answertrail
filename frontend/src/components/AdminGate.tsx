"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { useAccount } from "./AccountProvider";

/** Wraps an admin page. It only decides what the browser shows; the real protection is on the server,
 *  where every admin endpoint checks the login AND the administrator allowlist. */
export default function AdminGate({ children, loading }: { children: ReactNode; loading?: ReactNode }) {
  const account = useAccount();
  const pathname = usePathname();

  if (!account.configured) {
    return (
      <div className="panel">
        <strong>Sign-in isn&apos;t configured.</strong>
        <p className="hint">
          Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local, then restart the
          frontend.
        </p>
      </div>
    );
  }
  if (!account.ready) return <>{loading ?? <p className="hint">Checking your session…</p>}</>;

  if (!account.signedIn) {
    return (
      <div className="panel">
        <strong>Administrator sign-in required</strong>
        <p className="hint">Sign in with an administrator account to use this page.</p>
        <div className="row">
          <Link href={`/login?as=admin&next=${encodeURIComponent(pathname)}`} className="btn btn-primary btn-sm">
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  if (!account.isAdmin) {
    return (
      <div className="panel">
        <strong>{account.error ?? "This account isn't an administrator."}</strong>
        <p className="hint">
          You&apos;re signed in as {account.email}. Only the administrator accounts set up for this project can use
          this page.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
