import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import AuthGuard from "@/components/AuthGuard";

export const metadata: Metadata = {
  title: "TeammateX",
  description: "Codebase agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen overflow-hidden bg-[#1e1e24]">
        <AuthGuard>
          <Sidebar />
          <main className="flex-1 overflow-y-auto">{children}</main>
        </AuthGuard>
      </body>
    </html>
  );
}
