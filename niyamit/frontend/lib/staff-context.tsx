"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, usePoll } from "@/lib/api";
import type { Dashboard, Me } from "@/lib/types";

type StaffState = { me: Me; counts: Dashboard | null; refreshCounts: () => void; can: (perm: string) => boolean };

const StaffContext = createContext<StaffState | null>(null);

export function StaffProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [counts, setCounts] = useState<Dashboard | null>(null);

  useEffect(() => {
    api<Me>("/v1/auth/me")
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      });
  }, [router, pathname]);

  const refreshCounts = useCallback(() => {
    if (!me || me.user.role === "OPERATOR") return;
    api<Dashboard>("/v1/dashboard").then(setCounts).catch(() => undefined);
  }, [me]);

  useEffect(() => refreshCounts(), [refreshCounts, pathname]);
  usePoll(Boolean(me), refreshCounts, 30000);

  if (!me) return <p className="muted" style={{ padding: 28 }}>Loading…</p>;
  const can = (perm: string) => me.permissions.includes(perm);
  return <StaffContext.Provider value={{ me, counts, refreshCounts, can }}>{children}</StaffContext.Provider>;
}

export function useStaff(): StaffState {
  const ctx = useContext(StaffContext);
  if (!ctx) throw new Error("useStaff must be used inside StaffProvider");
  return ctx;
}
