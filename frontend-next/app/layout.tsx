import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { Navbar } from "@/components/navbar"
import { CommandPalette } from "@/components/command-palette"
import { ReactQueryProvider } from "@/providers/react-query"
import { AuthGuard } from "@/components/auth-guard"
import { ToastProvider } from "@/lib/toast-context"
import { ToastContainer } from "@/components/toast-container"
import { LayoutClient } from "@/components/layout-client"
import { ThemeProvider } from "@/contexts/theme-context"
import { LocaleProvider } from "@/contexts/locale-context"

const inter = Inter({ subsets: ["latin"], variable: "--font-geist-sans" })

export const metadata: Metadata = {
  title: "AiFactChecker - AI-Powered Fact Checking",
  description: "AI-powered fact checking platform with document processing and verification",
  icons: {
    icon: "/favicon.svg",
    apple: "/pizza-icon.svg",
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.variable}>
        <ThemeProvider>
          <LocaleProvider>
            <ToastProvider>
              <ReactQueryProvider>
                <LayoutClient>
                  <AuthGuard>
                    <Navbar />
                    <CommandPalette />
                    <ToastContainer />
                    <main className="min-h-screen bg-background">
                      {children}
                    </main>
                  </AuthGuard>
                </LayoutClient>
              </ReactQueryProvider>
            </ToastProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
