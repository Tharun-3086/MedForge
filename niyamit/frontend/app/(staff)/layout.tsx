"use client";

import type { ReactNode } from "react";

import { StaffShell } from "@/components/staff-shell";
import { StaffProvider } from "@/lib/staff-context";

export default function StaffLayout({ children }: { children: ReactNode }) {
  return (
    <StaffProvider>
      <StaffShell>{children}</StaffShell>
    </StaffProvider>
  );
}
