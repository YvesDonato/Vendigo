import Image from "next/image";
import Link from "next/link";
import logo from "../../public/brand/vendigo-logo.png";

export function Brand({ href = "/", compact = false }: { href?: string; compact?: boolean }) {
  return <Link href={href} className={`brand ${compact ? "brand-compact" : ""}`} aria-label="Vendigo home">
    <Image className="brand-logo" src={logo} alt="VendiGo" sizes="200px" loading="eager" />
  </Link>;
}
