"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { useAccount } from "@/components/AccountProvider";
import { safeNext } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";

type Mode = "signin" | "signup" | "reset";

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary so the rest of the page can render statically.
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const resetDone = params.get("reset") === "done"; // just changed a password via the emailed link
  const adminEntry = params.get("as") === "admin"; // reached from an admin page: sign-in only, no sign-up
  const account = useAccount();
  const supabase = getSupabase();

  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<{ kind: "confirm" | "reset"; email: string } | null>(null);

  function switchMode(m: Mode) {
    setMode(m);
    setError(null);
    setSentTo(null);
    setPassword("");
    setShowPw(false);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    const address = email.trim();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") {
        const { error: err } = await supabase.auth.signInWithPassword({ email: address, password });
        if (err?.code === "email_not_confirmed") {
          // Supabase only says this when the password was right, so it reveals nothing an attacker could use.
          setError("Please confirm your email first: open the link we sent you, then sign in.");
        } else if (err) {
          // Deliberately vague: don't reveal whether the email has an account.
          setError(
            `That email and password didn't match. Check both, or use "Forgot your password?" below. (Supabase says: ${err.code ?? err.status ?? "unknown"})`,
          );
        } else router.replace(next);
      } else if (mode === "signup") {
        const fullName = name.trim().replace(/\s+/g, " ");
        if (fullName.length < 2 || fullName.length > 60) {
          setError("Please enter your name (2 to 60 characters).");
          return;
        }
        if (password.length < 8) {
          setError("Use a password of at least 8 characters.");
          return;
        }
        const { data, error: err } = await supabase.auth.signUp({
          email: address,
          password,
          options: { emailRedirectTo: `${window.location.origin}/chat`, data: { full_name: fullName } },
        });
        if (err) {
          setError(
            err.code === "signup_disabled"
              ? "New sign-ups are switched off for this project right now. Please try again later."
              : err.message,
          );
        } else if (data.session) router.replace(next); // email confirmation is switched off in Supabase
        else setSentTo({ kind: "confirm", email: address });
      } else {
        const { error: err } = await supabase.auth.resetPasswordForEmail(address, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
        if (err) setError(err.message);
        else setSentTo({ kind: "reset", email: address });
      }
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  if (!supabase) {
    return (
      <div className="page narrow">
        <div className="panel">
          <strong>Sign-in isn&apos;t configured.</strong>
          <p className="hint">
            Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local, then restart the
            frontend.
          </p>
        </div>
      </div>
    );
  }

  if (account.signedIn) {
    return (
      <div className="page narrow">
        <div className="panel">
          <h1 className="page-title small">You&apos;re signed in</h1>
          <p className="hint">
            Signed in as <strong>{account.name ?? account.email}</strong>
            {account.name && <> ({account.email})</>}.
          </p>
          <div className="row">
            <Link href={next} className="btn btn-primary btn-sm">
              Continue
            </Link>
            <button className="ghost-btn" onClick={() => void supabase.auth.signOut()}>
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  const title = adminEntry ? "Administrator sign-in" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create an account" : "Reset your password";

  return (
    <div className="page narrow">
      <header className="page-head">
        <h1 className="page-title">{title}</h1>
        {mode === "reset" && (
          <p className="page-sub">Enter your email and we&apos;ll send you a link to choose a new password.</p>
        )}
        {adminEntry && mode === "signin" && (
          <p className="page-sub">
            For the administrator accounts of this project. Administrator accounts are set up by the project
            owner, so there is no sign-up here.
          </p>
        )}
      </header>

      {mode !== "reset" && !adminEntry && (
        <aside className="why" aria-label="Why create an account">
          <strong>{mode === "signup" ? "Why create an account?" : "Why sign in?"}</strong>
          <ul>
            <li>
              <b>Your chats are private.</b> Only your account can open them. Without an account, anyone who has a
              chat&apos;s link can read it.
            </li>
            <li>
              <b>Pick up on any device.</b> Your recent chats appear in the sidebar wherever you sign in.
            </li>
            <li>
              <b>Nothing is lost.</b> Chats you started before signing in are moved into your account.
            </li>
          </ul>
          <p className="hint">You don&apos;t need an account to ask questions. It&apos;s optional.</p>
        </aside>
      )}

      {sentTo ? (
        <div className="notice ok" role="status">
          {sentTo.kind === "confirm" ? (
            <>
              We sent a confirmation link to <strong>{sentTo.email}</strong>. Open it to finish creating your account,
              then come back and sign in. Check your spam folder if it doesn&apos;t arrive.
            </>
          ) : (
            <>
              If <strong>{sentTo.email}</strong> has an account, a link to reset the password is on its way. Check your
              spam folder too.
            </>
          )}
        </div>
      ) : (
        <>
          {resetDone && mode === "signin" && !error && (
            <div className="notice ok" role="status">
              Your password has been changed. Sign in with your new password.
            </div>
          )}
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          <form className="panel" onSubmit={submit}>
            {mode === "signup" && (
              <>
                <label htmlFor="name">Your name</label>
                <div className="row">
                  <input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="name"
                    maxLength={60}
                    required
                  />
                </div>
                <label htmlFor="email" className="spaced">
                  Email
                </label>
              </>
            )}
            {mode !== "signup" && <label htmlFor="email">Email</label>}
            <div className="row">
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            {mode !== "reset" && (
              <>
                <label htmlFor="password" className="spaced">
                  Password
                </label>
                <div className="row">
                  <div className="pw-wrap">
                    <input
                      id="password"
                      type={showPw ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete={mode === "signin" ? "current-password" : "new-password"}
                      minLength={mode === "signup" ? 8 : undefined}
                      required
                    />
                    <button type="button" className="pw-toggle" onClick={() => setShowPw((v) => !v)} aria-pressed={showPw}>
                      {showPw ? "Hide" : "Show"}
                    </button>
                  </div>
                </div>
                {mode === "signup" && <p className="hint">At least 8 characters.</p>}
              </>
            )}
            <div className="row">
              <button type="submit" disabled={busy}>
                {busy ? "…" : mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
              </button>
            </div>
          </form>
        </>
      )}

      <div className="auth-links">
        {mode === "signin" && (
          <>
            {!adminEntry && (
              <button className="link" onClick={() => switchMode("signup")}>
                Create an account
              </button>
            )}
            <button className="link" onClick={() => switchMode("reset")}>
              Forgot your password?
            </button>
          </>
        )}
        {mode !== "signin" && (
          <button className="link" onClick={() => switchMode("signin")}>
            Back to sign in
          </button>
        )}
      </div>
    </div>
  );
}
