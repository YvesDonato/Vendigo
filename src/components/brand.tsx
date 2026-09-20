import Link from "next/link";

export function Brand({ href = "/", compact = false }: { href?: string; compact?: boolean }) {
  return <Link href={href} className={`brand ${compact ? "brand-compact" : ""}`} aria-label="Vendigo home">
    <span className="brand-mark"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="M5 12L20 19L35 8L28 25L20 34L14 23Z" fill="currentColor" /><path d="M22 19L32 17L27 24" fill="#fff" opacity=".85" /></svg></span>
    <span>Vendigo</span>
  </Link>;
}
