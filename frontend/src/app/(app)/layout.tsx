import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

// Chat, Evaluation and Admin share one frame: top bar + side navbar.
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
