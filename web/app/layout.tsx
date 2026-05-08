import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "News Tracker",
  description: "Track article revisions by title, body, image, and deletion state."
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            News Tracker
          </Link>
        </header>
        {children}
      </body>
    </html>
  );
}
