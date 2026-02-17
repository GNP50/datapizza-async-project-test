"use client"

import { useToast } from "@/lib/toast-context"
import { AlertCircle, CheckCircle, Info, X } from "lucide-react"
import { cn } from "@/lib/utils"

export function ToastContainer() {
  const { toasts, removeToast } = useToast()

  return (
    <div className="fixed top-4 left-4 z-[9999] space-y-2 pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "pointer-events-auto flex items-center gap-3 rounded-lg px-4 py-3 shadow-lg animate-in fade-in slide-in-from-top-2 duration-200",
            toast.type === "error"
              ? "bg-red-500 text-white"
              : toast.type === "success"
                ? "bg-green-500 text-white"
                : "bg-blue-500 text-white"
          )}
        >
          <div className="flex-shrink-0">
            {toast.type === "error" && <AlertCircle className="h-5 w-5" />}
            {toast.type === "success" && <CheckCircle className="h-5 w-5" />}
            {toast.type === "info" && <Info className="h-5 w-5" />}
          </div>
          <span className="text-sm font-medium">{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            className="ml-auto flex-shrink-0 hover:opacity-80 transition-opacity"
            aria-label="Close toast"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}
