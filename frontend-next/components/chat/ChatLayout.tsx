"use client"

import * as React from "react"
import { Message, Document, Fact } from "@/lib/api"
import { Sidebar } from "./Sidebar"

interface ChatLayoutProps {
  messages: Message[]
  sidebarOpen: boolean
  onSidebarToggle: (open: boolean) => void
  highlightedMessageId?: string | null
  onClearFilter?: () => void
  onDocumentReprocess?: (documentId: string) => void
  onDocumentStop?: (documentId: string) => void
  onGenerateFlashcards?: (documentId: string) => void
  children: React.ReactNode
}

export function ChatLayout({
  messages,
  sidebarOpen,
  onSidebarToggle,
  highlightedMessageId,
  onClearFilter,
  onDocumentReprocess,
  onDocumentStop,
  onGenerateFlashcards,
  children
}: ChatLayoutProps) {
  // Aggregate all documents from messages
  const allDocuments = React.useMemo(() => {
    const docsMap = new Map<string, Document>()
    messages.forEach(msg => {
      msg.documents?.forEach(doc => {
        docsMap.set(doc.id, doc)
      })
    })
    return Array.from(docsMap.values())
  }, [messages])

  // Extract all facts from documents
  const allFacts = React.useMemo(() => {
    const factsArray: Fact[] = []
    allDocuments.forEach(doc => {
      doc.facts?.forEach(fact => {
        factsArray.push(fact)
      })
    })
    return factsArray
  }, [allDocuments])

  return (
    <div className="chat-layout">
      <div className={`chat-layout-main ${sidebarOpen ? 'chat-layout-main-with-sidebar' : ''}`}>
        {children}
      </div>

      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => onSidebarToggle(false)}
        documents={allDocuments}
        facts={allFacts}
        highlightedMessageId={highlightedMessageId}
        onClearFilter={onClearFilter}
        onDocumentReprocess={onDocumentReprocess}
        onDocumentStop={onDocumentStop}
        onGenerateFlashcards={onGenerateFlashcards}
      />
    </div>
  )
}
