"use client"

import { useEffect } from "react"
import { useToast } from "@/lib/toast-context"

export function useConnectionError() {
  const { addToast } = useToast()

  useEffect(() => {
    const handleConnectionError = () => {
      addToast("Connection error: Unable to reach the server", "error", 5000)
    }

    window.addEventListener("connectionError", handleConnectionError)
    return () => window.removeEventListener("connectionError", handleConnectionError)
  }, [addToast])
}
