"use client";
import Link from "next/link";
import { useApi } from "@/lib/api";

export function DemoEntrypoints() {
  const { data, loading, error, reload } = useApi<{demo_available:boolean}>("/v1/p/otp/config");
  if (loading) return <p className="small muted" role="status">Checking demo access…</p>;
  if (error) return <div className="notice stack"><p>Demo access could not be checked. The service may still be waking up.</p><button type="button" className="btn btn--quiet" onClick={()=>void reload()}>Retry demo access</button></div>;
  if (!data?.demo_available) return null;
  return <section className="panel stack" aria-labelledby="demo-access-title"><h2 id="demo-access-title">Explore the demo</h2><p>Try the connected patient and clinic experience with shared synthetic accounts. Use fictional documents only.</p><div className="row"><Link className="btn" href="/patient#demo-patient">Try demo patient — no OTP</Link><Link className="btn btn--quiet" href="/login#demo-accounts">Try demo clinics</Link></div></section>;
}
