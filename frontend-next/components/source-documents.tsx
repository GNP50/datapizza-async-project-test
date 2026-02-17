"use client"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Document, FactCheck } from "@/lib/api"
import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp, Clock, FileText, Loader2, XCircle } from "lucide-react"
import * as React from "react"

interface SourceDocumentsProps {
  documents: Document[]
  factChecks: FactCheck[]
}

export function SourceDocuments({ documents, factChecks }: SourceDocumentsProps) {
  const [isExpanded, setIsExpanded] = React.useState(false)

  if (documents.length === 0 && factChecks.length === 0) {
    return null
  }

  const getConfidenceLevel = (score: number) => {
    if (score >= 0.7) return { label: "High", class: "confidence-high" }
    if (score >= 0.4) return { label: "Medium", class: "confidence-medium" }
    return { label: "Low", class: "confidence-low" }
  }

  const getVerificationIcon = (status: string) => {
    switch (status) {
      case "verified":
        return <CheckCircle2 className="h-4 w-4 status-verified" />
      case "debunked":
        return <XCircle className="h-4 w-4 status-debunked" />
      case "uncertain":
        return <AlertCircle className="h-4 w-4 status-uncertain" />
      default:
        return <AlertCircle className="h-4 w-4 text-slate-400" />
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const getProcessingStateDisplay = (state: string) => {
    switch (state) {
      case "pending":
        return { label: "Pending", icon: <Clock className="h-3 w-3" />, variant: "secondary" as const }
      case "ocr_extraction":
        return { label: "Extracting", icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" as const }
      case "fact_atomization":
        return { label: "Analyzing", icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" as const }
      case "web_verification":
        return { label: "Verifying", icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" as const }
      case "qa_generation":
        return { label: "Generating Q&A", icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" as const }
      case "vector_indexing":
        return { label: "Indexing", icon: <Loader2 className="h-3 w-3 animate-spin" />, variant: "default" as const }
      case "completed":
        return { label: "Completed", icon: <CheckCircle2 className="h-3 w-3" />, variant: "default" as const }
      case "failed":
        return { label: "Failed", icon: <XCircle className="h-3 w-3" />, variant: "destructive" as const }
      default:
        return { label: "Unknown", icon: <AlertCircle className="h-3 w-3" />, variant: "secondary" as const }
    }
  }

  return (
    <div className="source-documents-wrapper">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="source-documents-toggle"
        type="button"
      >
        {isExpanded ? (
          <>
            <ChevronUp className="h-3 w-3" />
            <span>Hide sources</span>
          </>
        ) : (
          <>
            <ChevronDown className="h-3 w-3" />
            <span>
              View sources ({documents.length} {documents.length === 1 ? "document" : "documents"}
              {factChecks.length > 0 && `, ${factChecks.length} fact checks`})
            </span>
          </>
        )}
      </button>

      {isExpanded && (
        <div className="source-documents-panel">
          {/* Documents Section */}
          {documents.length > 0 && (
            <div>
              <div className="source-documents-header">
                <FileText className="h-4 w-4" />
                <span>Referenced Documents</span>
              </div>
              <div className="source-documents-list">
                {documents.map((doc) => {
                  const stateDisplay = getProcessingStateDisplay(doc.processing_state)
                  return (
                    <Card key={doc.id} className="source-document-item">
                      <div className="source-document-name">{doc.filename}</div>
                      <div className="source-document-meta">
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>•</span>
                        <span>{doc.mime_type}</span>
                        <span>•</span>
                        <Badge variant={stateDisplay.variant} className="text-xs flex items-center gap-1">
                          {stateDisplay.icon}
                          {stateDisplay.label}
                        </Badge>
                      </div>
                    </Card>
                  )
                })}
              </div>
            </div>
          )}

          {/* Fact Checks Section */}
          {factChecks.length > 0 && (
            <div className={documents.length > 0 ? "mt-4" : ""}>
              <div className="source-documents-header">
                <CheckCircle2 className="h-4 w-4" />
                <span>Fact Checks</span>
              </div>
              <div className="fact-checks-container">
                {factChecks.map((check) => {
                  const confidence = getConfidenceLevel(check.confidence_score)
                  return (
                    <Card key={check.id} className="fact-check-item">
                      <div className="fact-check-claim">&ldquo;{check.claim}&rdquo;</div>
                      <div className="fact-check-status">
                        {getVerificationIcon(check.verification_status)}
                        <span className="capitalize">{check.verification_status}</span>
                        <span>•</span>
                        <span className={`source-document-confidence ${confidence.class}`}>
                          {confidence.label} Confidence ({Math.round(check.confidence_score * 100)}%)
                        </span>
                      </div>
                      {check.sources && Object.keys(check.sources).length > 0 && (
                        <div className="mt-2 text-xs text-slate-600">
                          <strong>Sources:</strong>{" "}
                          {Object.entries(check.sources).map(([key, value], idx) => (
                            <span key={key}>
                              {idx > 0 && ", "}
                              {String(value)}
                            </span>
                          ))}
                        </div>
                      )}
                    </Card>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
