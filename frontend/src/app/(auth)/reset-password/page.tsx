"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useAccount } from "@/components/AccountProvider";
import { getSupabase } from "@/lib/supabase";

/** The page the password-reset email links to. Supabase signs the person in from the link (a recovery
 *  session); this page then lets them choose the new password. */
export default function ResetPasswordPage() {
  const router = useRouter();
  const account = useAccount();
  const supabase = getSupabase();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    if (password.length < 8) {
      setError("Use a password of at least 8 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    const { error: err } = await supabase.auth.updateUser({ password });
    setPassword("");
    if (err) {
      setError(err.message);
      setBusy(false);
      return;
    }
    // The link signed this browser in only so the password could be changed. End that session and ask
    // for the new password at the sign-in page: it proves the change worked and leaves nobody signed in
    // on a shared computer just because they opened an email.
    await supabase.auth.signOut({ scope: "local" });
    router.replace("/login?reset=done");
  }

  return (
    <div className="page narrow">
      <header className="page-head">
        <h1 className="page-title">Reset your password</h1>
        <p className="page-sub">Choose a new password for your account.</p>
      </header>

      {!account.ready ? (
        <p className="hint">Checking your link…</p>
      ) : !account.signedIn ? (
        <div className="panel">
          <strong>This link is invalid or has expired.</strong>
          <p className="hint">Reset links work once and for a limited time.</p>
          <div className="row">
            <Link href="/login" className="btn btn-primary btn-sm">
              Request a new link
            </Link>
          </div>
        </div>
      ) : (
        <>
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          <form className="panel" onSubmit={submit}>
            <label htmlFor="password">New password</label>
            <div className="row">
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </div>
            <p className="hint">At least 8 characters.</p>
            <div className="row">
              <button type="submit" disabled={busy}>
                {busy ? "Resetting…" : "Reset password"}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  );
}
