"use client"

import * as React from "react"
import { Button } from "@/components/ui/button"

interface AlertDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  actionLabel?: string
  cancelLabel?: string
  onAction: () => void
  variant?: "default" | "destructive"
}

export function AlertDialog({
  open,
  onOpenChange,
  title,
  description,
  actionLabel = "Continue",
  cancelLabel = "Cancel",
  onAction,
  variant = "default"
}: AlertDialogProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />

      {/* Dialog */}
      <div className="relative z-50 w-full max-w-lg mx-4 bg-white rounded-lg shadow-xl p-6">
        <h2 className="text-xl font-semibold text-slate-900 mb-2">
          {title}
        </h2>
        <p className="text-slate-600 mb-6">
          {description}
        </p>
        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={variant}
            onClick={() => {
              onAction()
              onOpenChange(false)
            }}
          >
            {actionLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
