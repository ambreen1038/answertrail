import type { Metadata } from "next";
import AccountProvider from "@/components/AccountProvider";
import { SITE_URL } from "@/lib/site";
import "./globals.css";

const TITLE = "AnswerTrail: AI customer support assistant";
const DESCRIPTION =
  "Support answers you can trace to the source. Answers only from a help center, cites the exact passages, and says so when it doesn't know.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: { title: TITLE, description: DESCRIPTION, type: "website", siteName: "AnswerTrail" },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <noscript>
          <style>{`.reveal{opacity:1}`}</style>
        </noscript>
        <AccountProvider>{children}</AccountProvider>
      </body>
    </html>
  );
}
