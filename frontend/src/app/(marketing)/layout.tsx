import Link from "next/link";
import type { ReactNode } from "react";
import Brand from "@/components/Brand";
import MarketingNav from "@/components/MarketingNav";
import { AUTHOR, REPO_URL } from "@/lib/site";

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <MarketingNav />
      {children}
      <footer className="mfoot">
        <div className="mfoot-inner">
          <Brand />
          <p>
            A retrieval-augmented support assistant by {AUTHOR}. The demo knowledge base is the help center of
            InvoiceFlow, a separate project.
          </p>
          <nav aria-label="Footer">
            <Link href="/chat">Demo</Link>
            <Link href="/evaluation">Evaluation</Link>
            <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
            <Link href="/privacy">Privacy</Link>
          </nav>
        </div>
      </footer>
    </>
  );
}
