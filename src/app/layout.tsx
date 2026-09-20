import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Vendigo — Commerce that comes to you.", template: "%s | Vendigo" },
  description: "Your autonomous storefront has arrived. Cold drinks, good snacks, and a little break, right where you are.",
  applicationName: "Vendigo",
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
