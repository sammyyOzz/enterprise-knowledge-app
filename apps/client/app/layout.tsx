import type { Metadata } from "next";
import { Instrument_Sans, Newsreader } from "next/font/google";
import { Shell } from "@/components/Shell";
import { WorkspaceProvider } from "@/lib/workspace";
import "./globals.css";

// Two clearly different families: a text serif for anything you read (answers, headings),
// and a plain sans for the interface around it.
const ui = Instrument_Sans({ subsets: ["latin"], variable: "--font-ui", display: "swap" });
const read = Newsreader({ subsets: ["latin"], variable: "--font-read", display: "swap" });

export const metadata: Metadata = {
  title: "Enterprise Knowledge",
  description: "Ask questions about your company's documents and get answers with sources.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ui.variable} ${read.variable}`}>
      <body>
        <WorkspaceProvider>
          <Shell>{children}</Shell>
        </WorkspaceProvider>
      </body>
    </html>
  );
}