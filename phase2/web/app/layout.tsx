import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Haemophilia Intelligence Radar",
  description: "Monitored haemophilia intelligence with evidence-backed assistants",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
