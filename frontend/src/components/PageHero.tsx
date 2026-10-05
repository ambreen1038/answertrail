import type { ReactNode } from "react";

/** The animated banner at the top of the app pages: an eyebrow line, the page title, a sentence about
 *  the page, and an optional slot (tabs, chips) underneath. `compact` is the slim version for the chat. */
export default function PageHero({
  eyebrow,
  title,
  subtitle,
  compact = false,
  children,
}: {
  eyebrow?: string;
  title: string;
  subtitle: string;
  compact?: boolean;
  children?: ReactNode;
}) {
  return (
    <header className={`dash-hero${compact ? " compact" : ""}`}>
      <div className="dash-hero-text">
        {eyebrow && <div className="dash-eyebrow">{eyebrow}</div>}
        <h1 className="dash-title">{title}</h1>
        <p className="dash-sub">{subtitle}</p>
      </div>
      {children}
      <span className="dash-orb dash-orb-a" aria-hidden="true" />
      <span className="dash-orb dash-orb-b" aria-hidden="true" />
    </header>
  );
}
