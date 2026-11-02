"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BrandMark } from "@/components/ui";
import { api } from "@/lib/api";
import { useStaff } from "@/lib/staff-context";
import type { Dashboard } from "@/lib/types";

type NavItem = { href: string; label: string; perm: string | null; demoOnly?: boolean; count?: (d: Dashboard) => number };
const NAV: { group: string | null; items: NavItem[] }[] = [
  {
    group: null,
    items: [
      { href: "/today", label: "Today", perm: "patients" },
      { href: "/tasks", label: "Tasks", perm: "tasks", count: (d) => d.open_tasks },
      { href: "/reports", label: "Report inbox", perm: "intake", count: (d) => d.documents_to_review },
      { href: "/patients", label: "Patients", perm: "patients" },
      { href: "/schedule", label: "Schedule", perm: "patients" },
      { href: "/messages", label: "Messages", perm: "messages", count: (d) => d.failed_messages_7d },
    ],
  },
  {
    group: "Demo tools",
    items: [
      { href: "/phone", label: "Patient phone (simulated)", perm: "patients", demoOnly: true },
      { href: "/test-panel", label: "Test panel", perm: "demo", demoOnly: true },
      { href: "/evaluation", label: "Language evaluation", perm: "evals" },
    ],
  },
  {
    group: "Clinic",
    items: [
      { href: "/metrics", label: "Metrics", perm: "metrics" },
      { href: "/settings", label: "Settings", perm: null },
      { href: "/audit", label: "Audit log", perm: "audit" },
    ],
  },
];

export function StaffShell({ children }: { children: ReactNode }) {
  const { me, counts, can } = useStaff();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (me.user.role === "OPERATOR" && pathname === "/today") router.replace("/metrics");
  }, [me.user.role, pathname, router]);

  async function signOut() {
    await api("/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  return (
    <div className="shell">
      <aside className={`rail${open ? " open" : ""}`} aria-label="Main">
        <Link href="/today" className="brand">
          <BrandMark />
          <span>
            <span className="brand-name">Niyamit</span>
            <span className="brand-sub" style={{ display: "block" }}>{me.clinic.short_name}</span>
          </span>
        </Link>
        <button className="btn btn--quiet btn--small menu-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          Menu
        </button>
        <nav className="nav">
          {NAV.map((section) => {
            const items = section.items.filter((i) => (i.perm === null || can(i.perm)) && (!i.demoOnly || me.demo_mode));
            if (!items.length) return null;
            return (
              <div key={section.group ?? "main"} style={{ display: "grid", gap: 2 }}>
                {section.group ? <div className="nav-group">{section.group}</div> : null}
                {items.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const n = counts && item.count ? item.count(counts) : 0;
                  return (
                    <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined}>
                      <span>{item.label}</span>
                      {n > 0 ? <span className="count">{n}</span> : null}
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <div className="rail-foot">
          <span>{me.user.name}</span>
          <span style={{ color: "#9fb3c6" }}>{me.user.role.charAt(0) + me.user.role.slice(1).toLowerCase()}</span>
          <button onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <div className="main">
        {me.demo_mode ? (
          <div className="demo-band" role="note">
            Demo mode: every patient here is synthetic and messages go to a simulated phone, not WhatsApp.
          </div>
        ) : null}
        <main className="page">{children}</main>
      </div>
    </div>
  );
}

export function PageHead({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="spread">
        <h1>{title}</h1>
        {actions ? <div className="row">{actions}</div> : null}
      </div>
      {lede ? <p className="lede">{lede}</p> : null}
    </header>
  );
}
