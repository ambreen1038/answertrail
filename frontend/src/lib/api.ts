import { API } from "./site";
import { getSupabase } from "./supabase";

/** fetch() for this app's API. If someone is signed in, their access token is attached (supabase-js
 *  refreshes it before it expires), which is how the server knows whose chats and which role they
 *  have. Anonymous visitors send no Authorization header at all. If the server rejects the token
 *  (401) the browser session is dropped, so the page falls back to the signed-out state. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const supabase = getSupabase();
  const token = supabase ? (await supabase.auth.getSession()).data.session?.access_token : undefined;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API}${path}`, { ...init, headers });
  if (res.status === 401 && token) await supabase?.auth.signOut();
  return res;
}

/** The server's own explanation of an error (FastAPI puts it in `detail`), or a fallback. */
export async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

/** Only allow redirecting to a path inside this site ("/chat"), never to another origin. */
export function safeNext(next: string | null, fallback = "/chat"): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\") ? next : fallback;
}
