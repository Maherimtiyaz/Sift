import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { Outfit, Syne } from "next/font/google";
import DemoModeNotice from "@/components/DemoModeNotice";
import LogoutButton from "@/components/LogoutButton";
import { COOKIE } from "@/lib/session";
import "./globals.css";

const syne = Syne({ subsets: ["latin"], weight: ["700", "800"], variable: "--f-display" });
const outfit = Outfit({ subsets: ["latin"], weight: ["400", "500"], variable: "--f-body" });

export const metadata: Metadata = {
  title: "Sift: voice note to everything",
  description: "Ramble for two minutes. Get tasks, calendar items and a draft message, sorted.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const signedIn = (await cookies()).has(COOKIE);
  return (
    <html lang="en" className={`${syne.variable} ${outfit.variable}`}>
      <body>
        <header className="top">
          <Link href="/" className="logo">sift</Link>
          {signedIn && (
            <nav><Link href="/history">History</Link><Link href="/settings">Settings</Link><LogoutButton /></nav>
          )}
          {!signedIn && (
            <nav className="auth-nav">
              <Link href="/login">Log in</Link>
              <Link className="nav-cta" href="/signup">Sign up</Link>
            </nav>
          )}
        </header>
        <DemoModeNotice />
        {children}
      </body>
    </html>
  );
}
