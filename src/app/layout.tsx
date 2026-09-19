import type { Metadata, Viewport } from "next";
import { DeliveryProvider } from "@/context/DeliveryContext";
import "@/styles.css";

export const metadata: Metadata = {
  title: "AutoDash — Autonomous delivery",
  description: "Fast, on-demand delivery inside the venue.",
  applicationName: "AutoDash",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#f7fbfe",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <DeliveryProvider>{children}</DeliveryProvider>
      </body>
    </html>
  );
}
