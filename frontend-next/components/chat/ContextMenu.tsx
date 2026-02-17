"use client"

import * as React from "react"
import { RotateCw, Square, ExternalLink, BookOpen, RefreshCw } from "lucide-react"

interface ContextMenuProps {
  x: number
  y: number
  type: "message" | "document"
  isProcessing: boolean
  isCompleted?: boolean
  isCached?: boolean
  onRelaunch: () => void
  onStop: () => void
  onBypassCache?: () => void
  onViewDetails?: () => void
  onGenerateFlashcards?: () => void
  onClose: () => void
}

export function ContextMenu({ x, y, type, isProcessing, isCompleted, isCached, onRelaunch, onStop, onBypassCache, onViewDetails, onGenerateFlashcards, onClose }: ContextMenuProps) {
  const menuRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose()
      }
    }

    const handleScroll = () => {
      onClose()
    }

    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("scroll", handleScroll, true)

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("scroll", handleScroll, true)
    }
  }, [onClose])

  return (
    <div
      ref={menuRef}
      className="context-menu"
      style={{
        position: "fixed",
        top: `${y}px`,
        left: `${x}px`,
        zIndex: 9999,
      }}
    >
      {type === "document" && onViewDetails && (
        <button
          className="context-menu-item"
          onClick={() => {
            onViewDetails()
            onClose()
          }}
        >
          <ExternalLink className="h-4 w-4" />
          <span>View Details</span>
        </button>
      )}

      {type === "document" && isCompleted && onGenerateFlashcards && (
        <button
          className="context-menu-item"
          onClick={() => {
            onGenerateFlashcards()
            onClose()
          }}
        >
          <BookOpen className="h-4 w-4" />
          <span>Generate Flashcards</span>
        </button>
      )}

      {type === "message" && isCached && onBypassCache && (
        <button
          className="context-menu-item"
          onClick={() => {
            onBypassCache()
            onClose()
          }}
        >
          <RefreshCw className="h-4 w-4" />
          <span>Regenerate without Cache</span>
        </button>
      )}

      {isProcessing ? (
        <button
          className="context-menu-item context-menu-item-danger"
          onClick={() => {
            onStop()
            onClose()
          }}
        >
          <Square className="h-4 w-4" />
          <span>Stop</span>
        </button>
      ) : (
        <button
          className="context-menu-item"
          onClick={() => {
            onRelaunch()
            onClose()
          }}
        >
          <RotateCw className="h-4 w-4" />
          <span>Relaunch</span>
        </button>
      )}
    </div>
  )
}
