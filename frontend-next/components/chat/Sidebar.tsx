"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { X, FileText, Loader2, CheckCircle2, Clock, AlertCircle, XCircle, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Document, Fact } from "@/lib/api"
import { ContextMenu } from "./ContextMenu"

interface SidebarProps {
  isOpen: boolean
  onClose: () => void
  documents: Document[]
  facts: Fact[]
  highlightedMessageId?: string | null
  onClearFilter?: () => void
  onDocumentReprocess?: (documentId: string) => void
  onDocumentStop?: (documentId: string) => void
  onGenerateFlashcards?: (documentId: string) => void
}

export function Sidebar({ isOpen, onClose, documents, facts, highlightedMessageId, onClearFilter, onDocumentReprocess, onDocumentStop, onGenerateFlashcards }: SidebarProps) {
  const router = useRouter()
  const [contextMenu, setContextMenu] = React.useState<{
    x: number
    y: number
    documentId: string
    docProcessing: boolean
    docCompleted: boolean
  } | null>(null)

  const isDocProcessing = (state: string) =>
    state !== "completed" && state !== "failed"

  const getFileStatusIcon = (state: string) => {
    switch (state) {
      case "completed":
        return <CheckCircle2 className="h-4 w-4 text-green-600" />
      case "failed":
        return <XCircle className="h-4 w-4 text-red-600" />
      case "pending":
        return <Clock className="h-4 w-4 text-slate-400" />
      default:
        return <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
    }
  }

  const getFileStatus = (state: string) => {
    switch (state) {
      case "pending":
        return { label: "Pending", className: "bg-slate-100 text-slate-700", variant: "secondary" as const }
      case "ocr_extraction":
        return { label: "Extracting Text", className: "bg-blue-100 text-blue-700", variant: "default" as const }
      case "fact_atomization":
        return { label: "Analyzing Facts", className: "bg-blue-100 text-blue-700", variant: "default" as const }
      case "web_verification":
        return { label: "Verifying", className: "bg-blue-100 text-blue-700", variant: "default" as const }
      case "qa_generation":
        return { label: "Generating Q&A", className: "bg-blue-100 text-blue-700", variant: "default" as const }
      case "vector_indexing":
        return { label: "Indexing", className: "bg-blue-100 text-blue-700", variant: "default" as const }
      case "completed":
        return { label: "Completed", className: "bg-green-100 text-green-700", variant: "default" as const }
      case "failed":
        return { label: "Failed", className: "bg-red-100 text-red-700", variant: "destructive" as const }
      default:
        return { label: "Unknown", className: "bg-slate-100 text-slate-700", variant: "secondary" as const }
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getConfidenceLevel = (score: number) => {
    if (score >= 0.7) return { label: "High", className: "bg-green-100 text-green-700" }
    if (score >= 0.4) return { label: "Medium", className: "bg-yellow-100 text-yellow-700" }
    return { label: "Low", className: "bg-red-100 text-red-700" }
  }

  const getVerificationIcon = (status: string) => {
    switch (status) {
      case "verified":
        return <CheckCircle2 className="h-4 w-4 text-green-600" />
      case "debunked":
        return <AlertCircle className="h-4 w-4 text-red-600" />
      case "uncertain":
        return <AlertCircle className="h-4 w-4 text-yellow-600" />
      default:
        return <Clock className="h-4 w-4 text-slate-400" />
    }
  }

  const handleDocumentClick = (docId: string) => {
    router.push(`/documents/${docId}`)
  }

  const handleDocContextMenu = (e: React.MouseEvent, docId: string, docState: string) => {
    e.preventDefault()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      documentId: docId,
      docProcessing: isDocProcessing(docState),
      docCompleted: docState === "completed",
    })
  }

  // No filtering for facts since they belong to documents, not messages
  const relevantFacts = facts

  return (
    <>
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          type="document"
          isProcessing={contextMenu.docProcessing}
          isCompleted={contextMenu.docCompleted}
          onRelaunch={() => {
            if (onDocumentReprocess) onDocumentReprocess(contextMenu.documentId)
          }}
          onStop={() => {
            if (onDocumentStop) onDocumentStop(contextMenu.documentId)
          }}
          onViewDetails={() => router.push(`/documents/${contextMenu.documentId}`)}
          onGenerateFlashcards={() => {
            if (onGenerateFlashcards) onGenerateFlashcards(contextMenu.documentId)
          }}
          onClose={() => setContextMenu(null)}
        />
      )}

      <div className={`sidebar ${isOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
        <div className="sidebar-header">
          <div className="flex items-center gap-2 flex-1">
            <FileText className="h-5 w-5 text-indigo-600" />
            <h2 className="sidebar-title">Documents & Facts</h2>
            {highlightedMessageId && onClearFilter && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  onClearFilter()
                }}
                className="ml-auto text-xs text-indigo-600 hover:text-indigo-700 h-7"
              >
                Show All
              </Button>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="shrink-0 h-8 w-8"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="sidebar-content">
          {/* Documents Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <h3 className="sidebar-section-title">
                Uploaded Documents ({documents.length})
              </h3>
            </div>

            {documents.length === 0 ? (
              <div className="sidebar-empty-state">
                <FileText className="h-12 w-12 text-slate-300 mb-2" />
                <p className="text-sm text-slate-500 text-center">
                  No documents uploaded yet
                </p>
              </div>
            ) : (
              <div className="sidebar-document-list">
                {documents.map((doc) => {
                  const status = getFileStatus(doc.processing_state)

                  return (
                    <Card
                      key={doc.id}
                      className="sidebar-document-card"
                      onContextMenu={(e) => handleDocContextMenu(e, doc.id, doc.processing_state)}
                    >
                      <button
                        className="sidebar-document-button"
                        onClick={() => handleDocumentClick(doc.id)}
                      >
                        <div className="flex items-start gap-3 flex-1">
                          {getFileStatusIcon(doc.processing_state)}
                          <div className="flex-1 min-w-0">
                            <div className="sidebar-document-name">
                              {doc.filename}
                            </div>
                            <div className="sidebar-document-meta">
                              <span>{formatFileSize(doc.file_size)}</span>
                              <span>•</span>
                              <Badge variant={status.variant} className={`text-xs ${status.className}`}>
                                {status.label}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        <ExternalLink className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                      </button>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>

          {/* Facts Section */}
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <h3 className="sidebar-section-title">
                Atomic Facts ({facts.length})
              </h3>
            </div>

            {relevantFacts.length === 0 ? (
              <div className="sidebar-empty-state">
                <CheckCircle2 className="h-12 w-12 text-slate-300 mb-2" />
                <p className="text-sm text-slate-500 text-center">
                  No facts extracted yet
                </p>
              </div>
            ) : (

              <div className="sidebar-fact-list">
                {relevantFacts.map((fact) => {
                  const confidence = getConfidenceLevel(fact.confidence_score)

                  // web_source_url is now an array
                  const sourceUrls = fact.web_source_url || []

                  return (
                    <Card
                      key={fact.id}
                      className="sidebar-fact-card"
                    >
                      <div className="flex items-start gap-2 mb-2">
                        {getVerificationIcon(fact.verification_status)}
                        <p className="sidebar-fact-claim">
                          &ldquo;{fact.content}&rdquo;
                        </p>
                      </div>

                      <div className="sidebar-fact-meta">
                        <span className="capitalize text-slate-700 text-xs font-medium">
                          {fact.verification_status}
                        </span>
                        <span>•</span>
                        <Badge variant="secondary" className={`text-xs ${confidence.className}`}>
                          {confidence.label} ({Math.round(fact.confidence_score * 100)}%)
                        </Badge>
                        {fact.page_number && (
                          <>
                            <span>•</span>
                            <span className="text-xs text-slate-600">Page {fact.page_number}</span>
                          </>
                        )}
                      </div>

                      {sourceUrls.length > 0 && (
                        <div className="sidebar-fact-sources">
                          <strong className="text-xs font-medium text-slate-700">References:</strong>
                          <div className="mt-1 space-y-1">
                            {sourceUrls.map((url, idx) => (
                              <div key={idx} className="text-xs text-slate-600 flex items-start gap-1">
                                <span className="text-indigo-600">•</span>
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex-1 text-indigo-600 hover:text-indigo-800 hover:underline break-all"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {url}
                                </a>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {fact.verification_reasoning && (
                        <div className="mt-2 pt-2 border-t border-slate-200">
                          <p className="text-xs text-slate-600 italic">
                            {fact.verification_reasoning}
                          </p>
                        </div>
                      )}
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
