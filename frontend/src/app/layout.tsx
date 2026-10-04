import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AnswerTrail: AI customer support assistant",
  description:
    "Support answers you can trace to the source. Answers only from a help center, cites the exact passages, and says so when it doesn't know.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <noscript>
          <style>{`.reveal{opacity:1}`}</style>
        </noscript>
        {children}
      </body>
    </html>
  );
}
