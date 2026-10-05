import Link from "next/link";
import type { ReactNode } from "react";
import Brand from "@/components/Brand";

const POINTS = [
  { title: "Your chats are private", text: "Only your account can open them." },
  { title: "Pick up on any device", text: "Recent chats follow you wherever you sign in." },
  { title: "Nothing is lost", text: "Chats you started before signing in come with you." },
];

// Sign-in pages stand alone: no sidebar, no app navigation. Wide screens get a brand panel with a
// small animated demo of what the product does; phones get just the form.
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-split">
      <aside className="auth-art">
        <div className="art-top">
          <Brand />
        </div>

        <div className="art-body">
          <h2 className="art-title">
            Support answers you can <em>trace to the source.</em>
          </h2>

          {/* A tiny staged conversation: question, then answer, then the source it came from. */}
          <div className="art-chat" aria-hidden="true">
            <div className="art-q">How big can an uploaded file be?</div>
            <div className="art-a">
              <span className="art-typing">
                <i />
                <i />
                <i />
              </span>
              <span className="art-answer">Each file can be up to 10 MB.</span>
              <span className="art-src">Uploading files &middot; File size limit</span>
            </div>
            <div className="art-q art-q2">Can it read Arabic invoices?</div>
            <div className="art-a art-a2">
              <span className="art-answer">I couldn&apos;t find that in the help articles, so I don&apos;t want to guess.</span>
            </div>
          </div>

          <ul className="art-points">
            {POINTS.map((p) => (
              <li key={p.title}>
                <b>{p.title}</b>
                <span>{p.text}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* decorative trail: three points joined by a line that draws itself */}
        <svg className="art-trail" viewBox="0 0 400 200" aria-hidden="true">
          <path d="M30 170 C 120 150, 150 80, 230 90 S 340 40, 380 20" pathLength="1" />
          <circle cx="30" cy="170" r="7" />
          <circle cx="230" cy="90" r="7" />
          <circle cx="380" cy="20" r="9" />
        </svg>
      </aside>

      <div className="auth-side">
        <header className="auth-top">
          <span className="auth-brand-mobile">
            <Brand />
          </span>
          <Link href="/" className="top-link">
            &larr; Back to home
          </Link>
        </header>
        <main className="auth-main">
          <div className="page-enter">{children}</div>
        </main>
        <footer className="auth-foot">
          <Link href="/privacy">How your data is handled</Link>
        </footer>
      </div>
    </div>
  );
}
