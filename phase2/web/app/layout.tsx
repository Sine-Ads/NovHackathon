import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "./providers";
import { LeftNav } from "@/components/LeftNav";
import { TopBar } from "@/components/TopBar";

export const metadata: Metadata = {
  title: "Haemophilia Intelligence Radar",
  description: "Monitored haemophilia intelligence with evidence-backed assistants",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <LeftNav />
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
              <TopBar />
              <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
