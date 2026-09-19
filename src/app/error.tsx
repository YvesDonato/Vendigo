"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="loading-screen"><span className="eyebrow">HAWK-2-U</span><h1>A small bump in the road.</h1><p>We couldn’t load your storefront. Let’s give it another try.</p><button className="button button-primary" onClick={reset}>Try again</button></main>;
}
