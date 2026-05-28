import type { Metadata } from "next";
import "./globals.css";
import ShellLayout from "@/components/ShellLayout";
import AuthGuard from "@/components/AuthGuard";

export const metadata: Metadata = {
  title: "TeammateX",
  description: "Codebase agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="overflow-hidden">
        <AuthGuard>
          <ShellLayout>{children}</ShellLayout>
        </AuthGuard>
      </body>
    </html>
  );
}
