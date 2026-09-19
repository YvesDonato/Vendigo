"use client";

import Link from "next/link";
import { ArrowLeft, Radio } from "lucide-react";

type HeaderProps = {
  backHref?: string;
  step?: string;
};

export function Header({ backHref, step }: HeaderProps) {
  return (
    <header className="site-header">
      <div className="header-side">
        {backHref ? (
          <Link className="icon-button" href={backHref} aria-label="Go back">
            <ArrowLeft aria-hidden="true" size={19} strokeWidth={1.8} />
          </Link>
        ) : (
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
          </div>
        )}
      </div>
      <Link className="wordmark" href="/" aria-label="AutoDash home">
        AUTODASH
      </Link>
      <div className="header-side header-side-right">
        {step ? (
          <span className="step-label">{step}</span>
        ) : (
          <Radio className="header-radio" size={18} aria-hidden="true" />
        )}
      </div>
    </header>
  );
}
