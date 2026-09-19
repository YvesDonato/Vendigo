import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Hawk-2-U — Commerce that comes to you.", template: "%s | Hawk-2-U" },
  description: "Your autonomous storefront has arrived. Cold drinks, good snacks, and a little break, right where you are.",
  applicationName: "Hawk-2-U",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
