"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Message } from "@/lib/api"
import { AlertCircle, Bot, CheckCircle2, Clock, Database, FileText, Info, Loader2, Paperclip, RotateCw, Search, User as UserIcon, XCircle, Zap } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"
import { ContextMenu } from "./ContextMenu"
import { MarkdownRenderer } from "./MarkdownRenderer"

interface MessageBubbleProps {
  message: Message
  onVerifyClick?: () => void
  onRetry?: () => void
  onStop?: () => void
  onBypassCache?: () => void
  onDocumentReprocess?: (documentId: string) => void
  onDocumentStop?: (documentId: string) => void
  onGenerateFlashcards?: (documentId: string) => void
}

export function MessageBubble({ message, onVerifyClick, onRetry, onStop, onBypassCache, onDocumentReprocess, onDocumentStop, onGenerateFlashcards }: MessageBubbleProps) {
  const router = useRouter()
  const [contextMenu, setContextMenu] = React.useState<{
    x: number
    y: number
    type: "message" | "document"
    documentId?: string
    docProcessing?: boolean
    docCompleted?: boolean
  } | null>(null)
  const isUser = message.role === "user"
  const isFailed = message.processing_state === "failed"
  const isProcessing = message.processing_state !== "completed" && message.processing_state !== "failed"
  const hasVerifiableContent = message.role === "assistant" &&
                               message.processing_state === "completed" &&
                               (message.documents?.length > 0 || message.fact_checks?.length > 0)
  const hasDocuments = message.documents && message.documents.length > 0

  // Consider response as "cached" for UI purposes if it used the vector store
  // This includes: response_cached=true (semantic cache hit) OR response_type="rag" (vector store retrieval)
  const responseType = message.response_type || message.response_metadata?.response_type
  const isCached = message.response_cached ||
                   message.response_metadata?.cached ||
                   responseType === "cached" ||
                   responseType === "rag"

  const documentsUsed = message.response_metadata?.documents_used || []

  const isDocProcessing = (state: string) => {
    return state !== "completed" && state !== "failed"
  }

  const getProcessingStateIcon = (state: string) => {
    switch (state) {
      case "completed":
        return <CheckCircle2 className="h-3 w-3 text-green-600" />
      case "failed":
        return <XCircle className="h-3 w-3 text-red-600" />
      case "pending":
        return <Clock className="h-3 w-3 text-slate-400" />
      default:
        return <Loader2 className="h-3 w-3 animate-spin text-blue-600" />
    }
  }

  const getProcessingStateLabel = (state: string) => {
    switch (state) {
      case "pending": return "Pending"
      case "ocr_extraction": return "Extracting text..."
      case "fact_atomization": return "Analyzing facts..."
      case "web_verification": return "Verifying..."
      case "qa_generation": return "Generating Q&A..."
      case "vector_indexing": return "Indexing..."
      case "completed": return "Ready"
      case "failed": return "Failed"
      default: return state
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleContextMenu = (e: React.MouseEvent, type: "message" | "document", documentId?: string, docState?: string) => {
    e.preventDefault()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      type,
      documentId,
      docProcessing: docState ? isDocProcessing(docState) : false,
      docCompleted: docState === "completed",
    })
  }

  const handleDocumentClick = (documentId: string) => {
    router.push(`/documents/${documentId}`)
  }

  const handleRelaunch = () => {
    if (contextMenu?.type === "document" && contextMenu.documentId && onDocumentReprocess) {
      onDocumentReprocess(contextMenu.documentId)
    } else if (onRetry) {
      onRetry()
    }
  }

  const handleStop = () => {
    if (contextMenu?.type === "document" && contextMenu.documentId && onDocumentStop) {
      onDocumentStop(contextMenu.documentId)
    } else if (onStop) {
      onStop()
    }
  }

  const handleViewDetails = () => {
    if (contextMenu?.documentId) {
      router.push(`/documents/${contextMenu.documentId}`)
    }
  }

  const contextIsProcessing = contextMenu?.type === "document"
    ? !!contextMenu.docProcessing
    : isProcessing

  return (
    <>
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          type={contextMenu.type}
          isProcessing={contextIsProcessing}
          isCompleted={contextMenu.type === "document" ? !!contextMenu.docCompleted : false}
          isCached={contextMenu.type === "message" ? isCached : false}
          onRelaunch={handleRelaunch}
          onStop={handleStop}
          onBypassCache={contextMenu.type === "message" && isCached && onBypassCache ? onBypassCache : undefined}
          onViewDetails={contextMenu.type === "document" ? handleViewDetails : undefined}
          onGenerateFlashcards={contextMenu.type === "document" && contextMenu.documentId && onGenerateFlashcards
            ? () => onGenerateFlashcards(contextMenu.documentId!)
            : undefined}
          onClose={() => setContextMenu(null)}
        />
      )}
    <div className={`message-wrapper ${isUser ? "message-wrapper-user" : ""}`}>
      <div className={`message-avatar ${
        isUser ? "message-avatar-user" : "message-avatar-assistant"
      }`}>
        {isUser ? (
          <UserIcon className="h-5 w-5" />
        ) : (
          <Bot className="h-5 w-5 text-indigo-600" />
        )}
      </div>

      <div className={`message-content-wrapper ${
        isUser ? "message-content-wrapper-user" : "message-content-wrapper-assistant"
      }`}>
        {/* Document Attachments */}
        {hasDocuments && (
          <div className="message-attachments">
            <div className="flex items-center gap-1.5 text-xs text-slate-600 mb-1">
              <Paperclip className="h-3.5 w-3.5" />
              <span className="font-medium">
                {message.documents.length} {message.documents.length === 1 ? "attachment" : "attachments"}
              </span>
            </div>
            <div className="space-y-1.5">
              {message.documents.map((doc) => (
                <div
                  key={doc.id}
                  className="message-attachment-item message-attachment-item-clickable"
                  onClick={() => handleDocumentClick(doc.id)}
                  onContextMenu={(e) => handleContextMenu(e, "document", doc.id, doc.processing_state)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <FileText className="h-3.5 w-3.5 text-slate-500 flex-shrink-0" />
                    <span className="text-xs font-medium text-slate-700 truncate">
                      {doc.filename}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[10px] text-slate-400">
                      {getProcessingStateLabel(doc.processing_state)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {formatFileSize(doc.file_size)}
                    </span>
                    <div className="flex items-center gap-1">
                      {getProcessingStateIcon(doc.processing_state)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <Card
          className={`message-bubble ${
            isUser ? "message-bubble-user" : isFailed ? "message-bubble-error" : isCached ? "message-bubble-cached" : "message-bubble-assistant"
          }`}
          onContextMenu={(e) => handleContextMenu(e, "message")}
        >
          {/* Cache/Vector Store indicator */}
          {!isUser && isCached && (
            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-blue-200">
              <Zap className="h-3.5 w-3.5 text-blue-600" />
              <div className="flex-1 flex items-center gap-2">
                <span className="text-xs font-medium text-blue-700">
                  {responseType === "cached" ? "Semantic Cache" : "Vector Search"}
                </span>
                
              </div>
            </div>
          )}

          {isUser ? (
            <p className="message-text">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} className="message-text" />
          )}

          {/* Fact checks - only show if present */}
          {!isUser && message.fact_checks && message.fact_checks.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-200">
              <div className="flex items-center gap-1.5 mb-2">
                <Info className="h-3.5 w-3.5 text-slate-500" />
                <span className="text-xs font-medium text-slate-600">
                  Fact Checks ({message.fact_checks.length})
                </span>
              </div>
              <div className="space-y-2">
                {message.fact_checks.map((fact) => {
                  const getStatusColor = (status: string) => {
                    switch (status) {
                      case "verified": return "text-green-700 bg-green-50 border-green-200"
                      case "debunked": return "text-red-700 bg-red-50 border-red-200"
                      case "uncertain": return "text-yellow-700 bg-yellow-50 border-yellow-200"
                      default: return "text-slate-700 bg-slate-50 border-slate-200"
                    }
                  }

                  const getStatusIcon = (status: string) => {
                    switch (status) {
                      case "verified": return <CheckCircle2 className="h-3 w-3" />
                      case "debunked": return <XCircle className="h-3 w-3" />
                      case "uncertain": return <AlertCircle className="h-3 w-3" />
                      default: return <Clock className="h-3 w-3" />
                    }
                  }

                  return (
                    <div key={fact.id} className={`p-2 rounded-md border ${getStatusColor(fact.verification_status)}`}>
                      <div className="flex items-start gap-2">
                        <div className="mt-0.5">
                          {getStatusIcon(fact.verification_status)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium mb-1">{fact.claim}</p>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 capitalize">
                              {fact.verification_status}
                            </Badge>
                            {fact.confidence_score > 0 && (
                              <span className="text-[10px] text-slate-500">
                                {(fact.confidence_score * 100).toFixed(0)}% confidence
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Documents used */}
          {!isUser && documentsUsed.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-200">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Database className="h-3.5 w-3.5 text-slate-500" />
                <span className="text-xs font-medium text-slate-600">
                  Sources ({documentsUsed.length})
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {documentsUsed.map((doc: {id: string, filename: string}) => (
                  <Badge
                    key={doc.id}
                    variant="outline"
                    className="text-[10px] px-2 py-0.5 cursor-pointer hover:bg-slate-100"
                    onClick={() => handleDocumentClick(doc.id)}
                  >
                    {doc.filename}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* Processing State */}
        {isProcessing && (
          <div className="message-processing-state">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="capitalize">{message.processing_state.replace(/_/g, " ")}</span>
          </div>
        )}

        {/* Error State with Retry */}
        {isFailed && onRetry && (
          <div className="message-error-state">
            <AlertCircle className="h-4 w-4 text-red-600" />
            <span className="text-red-700">Processing failed</span>
            <Button
              variant="ghost"
              size="sm"
              className="message-retry-button"
              onClick={onRetry}
            >
              <RotateCw className="h-3.5 w-3.5" />
              <span>Retry</span>
            </Button>
          </div>
        )}

        {/* Verify Button for Assistant Messages */}
        {hasVerifiableContent && onVerifyClick && (
          <Button
            variant="ghost"
            size="sm"
            className="message-verify-button"
            onClick={onVerifyClick}
          >
            <Search className="h-3.5 w-3.5" />
            <span>Verify / Sources</span>
          </Button>
        )}

        <div className="flex items-center gap-2 mt-1">
          <span className="message-timestamp">
            {new Date(message.created_at).toLocaleTimeString()}
          </span>

          {!isUser && message.processing_state === 'completed' && (
            <span className="text-[10px] text-slate-400 flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" />
              Completed
            </span>
          )}
        </div>
      </div>
    </div>
    </>
  )
}
