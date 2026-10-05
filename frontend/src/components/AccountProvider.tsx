"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { clearLocalChats, enterAccountMode, leaveAccountMode, localChatIds, setServerChats } from "@/lib/history";
import { API } from "@/lib/site";
import { getSupabase } from "@/lib/supabase";

export type Account = {
  /** false until we know who (if anyone) is signed in, and, when someone is, whether they are an admin */
  ready: boolean;
  /** false when the public Supabase settings are missing, so sign-in cannot work at all */
  configured: boolean;
  signedIn: boolean;
  email: string | null;
  /** the name given at sign-up, if any */
  name: string | null;
  isAdmin: boolean;
  error: string | null;
};

const Ctx = createContext<Account>({ ready: false, configured: false, signedIn: false, email: null, name: null, isAdmin: false, error: null });

export const useAccount = () => useContext(Ctx);

type Me = { id: string; email: string; isAdmin: boolean };

/** Knows who is signed in. The browser holds the Supabase session; the SERVER says whether that
 *  person is an admin (GET /api/me), so the sidebar never guesses a role from "being signed in". */
export default function AccountProvider({ children }: { children: ReactNode }) {
  const supabase = getSupabase();
  const [session, setSession] = useState<Session | null>(null);
  const [authKnown, setAuthKnown] = useState(!supabase); // with no Supabase settings there is nothing to wait for
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(null);

  const userId = session?.user.id ?? null;

  useEffect(() => {
    if (!supabase) return;
    // Fires once straight away with the stored session, then on every sign-in, sign-out and token refresh.
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      tokenRef.current = next?.access_token ?? null;
      setSession(next);
      setAuthKnown(true);
    });
    return () => data.subscription.unsubscribe();
  }, [supabase]);

  // Runs when a different person signs in or out (not on the hourly token refresh).
  useEffect(() => {
    if (!userId) {
      leaveAccountMode();
      return;
    }
    let stale = false;
    enterAccountMode();
    (async () => {
      const headers = { Authorization: `Bearer ${tokenRef.current}` };
      try {
        const res = await fetch(`${API}/api/me`, { headers });
        if (stale) return;
        if (!res.ok) {
          setMe(null);
          setError(res.status === 401 ? "Your session has expired. Please sign in again." : "Couldn't check your account.");
          return;
        }
        const info = await res.json();
        setMe({ id: userId, email: info.email, isAdmin: !!info.is_admin });
        setError(null);

        // Chats started before signing in move into the account, then the account's own list is shown.
        const local = localChatIds();
        if (local.length) {
          const claim = await fetch(`${API}/api/me/claim`, {
            method: "POST",
            headers: { ...headers, "Content-Type": "application/json" },
            body: JSON.stringify({ ids: local.slice(0, 30) }),
          });
          if (claim.ok) clearLocalChats();
        }
        const list = await fetch(`${API}/api/me/conversations`, { headers });
        if (!stale && list.ok) setServerChats(await list.json());
      } catch {
        if (!stale) {
          setMe(null);
          setError("Couldn't reach the server to check your account.");
        }
      }
    })();
    return () => {
      stale = true;
    };
  }, [userId]);

  const value = useMemo<Account>(() => {
    const checked = !!userId && me?.id === userId; // the server has answered for THIS user
    return {
      ready: authKnown && (!userId || checked || error !== null),
      configured: !!supabase,
      signedIn: !!userId,
      email: session?.user.email ?? null,
      name: typeof session?.user.user_metadata?.full_name === "string" ? session.user.user_metadata.full_name : null,
      isAdmin: checked && !!me?.isAdmin,
      error: userId ? error : null,
    };
  }, [authKnown, userId, me, error, supabase, session?.user.email, session?.user.user_metadata?.full_name]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
