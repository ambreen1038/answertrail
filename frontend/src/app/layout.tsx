import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Customer Support Assistant",
  description:
    "A support assistant that answers only from a help center, cites the exact sources, and says so when it doesn't know.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
