import Link from "next/link";

/** The logo mark: a trail of three connected points, i.e. an answer traced back to its sources. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--brand)" />
      <path d="M9 22 15 14 23 10" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" opacity=".55" />
      <circle cx="9" cy="22" r="2.6" fill="#fff" />
      <circle cx="15" cy="14" r="2.6" fill="#fff" />
      <circle cx="23" cy="10" r="3.2" fill="#fff" />
    </svg>
  );
}

export default function Brand({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="brandlink" aria-label="AnswerTrail home">
      <Mark />
      <span className="wordmark">
        Answer<span>Trail</span>
      </span>
    </Link>
  );
}
