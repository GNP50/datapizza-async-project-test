"use client"

import { useConnectionError } from "@/lib/use-connection-error"

export function LayoutClient({ children }: { children: React.ReactNode }) {
  useConnectionError()
  return <>{children}</>
}
