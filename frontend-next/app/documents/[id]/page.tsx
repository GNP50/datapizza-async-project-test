"use client"

import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Pagination } from "@/components/ui/pagination"
import { documentsApi, Fact } from "@/lib/api"
import { usePagination } from "@/lib/usePagination"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  RotateCw,
  Square,
  XCircle,
} from "lucide-react"
import { useParams, useRouter } from "next/navigation"
import * as React from "react"

const PIPELINE_STAGES = [
  { key: "pending", label: "Pending", icon: Clock },
  { key: "ocr_extraction", label: "OCR & Extraction", icon: FileText },
  { key: "fact_atomization", label: "Fact Analysis", icon: AlertCircle },
  { key: "web_verification", label: "Web Verification", icon: Globe },
  { key: "qa_generation", label: "Q&A Generation", icon: FileText },
  { key: "vector_indexing", label: "Indexing", icon: FileText },
  { key: "completed", label: "Completed", icon: CheckCircle2 },
]

function getStageIndex(state: string): number {
  const idx = PIPELINE_STAGES.findIndex((s) => s.key === state)
  return idx === -1 ? 0 : idx
}

function PipelineProgress({
  currentState,
  webSearchEnabled,
  onRelaunchFromStage,
  onEnableWebSearchAndRelaunch,
  isRelaunching,
}: {
  currentState: string
  webSearchEnabled: boolean
  onRelaunchFromStage: (stageKey: string) => void
  onEnableWebSearchAndRelaunch: () => void
  isRelaunching: boolean
}) {
  const currentIdx = getStageIndex(currentState)
  const isFailed = currentState === "failed"
  const isProcessing = currentState !== "completed" && currentState !== "failed"

  const [contextMenu, setContextMenu] = React.useState<{
    x: number
    y: number
    stageKey: string
    stageLabel: string
  } | null>(null)

  React.useEffect(() => {
    const handleClick = () => setContextMenu(null)
    const handleScroll = () => setContextMenu(null)
    if (contextMenu) {
      window.addEventListener("click", handleClick)
      window.addEventListener("scroll", handleScroll, true)
      return () => {
        window.removeEventListener("click", handleClick)
        window.removeEventListener("scroll", handleScroll, true)
      }
    }
  }, [contextMenu])

  const handleContextMenu = (e: React.MouseEvent, stageKey: string, stageLabel: string) => {
    // Don't show context menu for "completed" stage or while processing
    if (stageKey === "completed" || isProcessing) return
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, stageKey, stageLabel })
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex-1">
          <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <RotateCw className="h-5 w-5 text-indigo-600" />
            Processing Pipeline
          </h3>
          <p className="text-sm text-slate-500 mt-1">Track document processing stages</p>
          {!webSearchEnabled && (
            <div className="mt-2 flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded-md">
              <Globe className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-xs text-amber-800">
                  <span className="font-semibold">Web verification disabled</span> - Facts will not be verified against online sources.
                  Right-click the Web Verification stage to enable it.
                </p>
              </div>
            </div>
          )}
        </div>
        {isProcessing && (
          <Badge className="bg-indigo-100 text-indigo-700 border-indigo-200 px-3 py-1 flex-shrink-0">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            Processing...
          </Badge>
        )}
      </div>

      <div className="relative px-4 py-6">
        <div className="flex items-start justify-between">
          {PIPELINE_STAGES.map((stage, idx) => {
            let status: "done" | "active" | "pending" | "failed" | "disabled" = "pending"
            if (isFailed && idx === currentIdx) status = "failed"
            else if (idx < currentIdx) status = "done"
            else if (idx === currentIdx) status = currentState === "completed" ? "done" : "active"

            // Check if this is the web_verification stage and it's disabled
            const isWebVerificationDisabled = stage.key === "web_verification" && !webSearchEnabled
            if (isWebVerificationDisabled && status === "pending") {
              status = "disabled"
            }

            const canRelaunch = !isProcessing && stage.key !== "completed"

            return (
              <div
                key={stage.key}
                className={`flex flex-col items-center gap-3 relative flex-1 ${canRelaunch ? "cursor-context-menu" : ""}`}
                onContextMenu={(e) => handleContextMenu(e, stage.key, stage.label)}
              >
                <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all z-10 relative ${
                  status === "done" ? "bg-emerald-100 border-emerald-500 text-emerald-600 shadow-md" :
                  status === "active" ? "bg-indigo-100 border-indigo-500 text-indigo-600 ring-4 ring-indigo-100 shadow-lg scale-110" :
                  status === "failed" ? "bg-red-100 border-red-500 text-red-600 shadow-md" :
                  status === "disabled" ? "bg-amber-50 border-amber-300 text-amber-500 opacity-60" :
                  "bg-slate-100 border-slate-300 text-slate-400"
                }`}>
                  {status === "done" && <CheckCircle2 className="h-5 w-5" />}
                  {status === "active" && <Loader2 className="h-5 w-5 animate-spin" />}
                  {status === "failed" && <XCircle className="h-5 w-5" />}
                  {status === "disabled" && <Globe className="h-5 w-5 opacity-50" />}
                  {status === "pending" && <div className="h-3 w-3 rounded-full bg-current" />}

                  {/* Badge for disabled web verification */}
                  {isWebVerificationDisabled && (
                    <div className="absolute -top-1 -right-1 w-4 h-4 bg-amber-500 rounded-full flex items-center justify-center shadow-sm">
                      <span className="text-[8px] text-white font-bold">!</span>
                    </div>
                  )}
                </div>
                {idx < PIPELINE_STAGES.length - 1 && (
                  <div className={`absolute top-5 left-[calc(50%+20px)] right-[calc(-50%+20px)] h-0.5 transition-all ${
                    idx < currentIdx ? "bg-emerald-400" : "bg-slate-200"
                  }`} />
                )}
                <span className={`text-xs text-center leading-tight max-w-[80px] ${
                  status === "active" ? "font-bold text-slate-900" :
                  status === "disabled" ? "text-amber-600 font-medium" :
                  "text-slate-600"
                }`}>
                  {stage.label}
                  {isWebVerificationDisabled && (
                    <span className="block text-[10px] text-amber-600 font-normal mt-0.5">(Disabled)</span>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <div
          className="fixed z-50 bg-white border border-slate-200 rounded-lg shadow-xl py-1 min-w-[240px] animate-scale-in"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          <button
            className="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={(e) => {
              e.stopPropagation()
              onRelaunchFromStage(contextMenu.stageKey)
              setContextMenu(null)
            }}
            disabled={isRelaunching}
          >
            <RotateCw className={`h-4 w-4 ${isRelaunching ? "animate-spin" : ""}`} />
            <span>Relaunch from {contextMenu.stageLabel}</span>
          </button>

          {/* Show "Enable Web Search" option only for web_verification stage when it's disabled */}
          {contextMenu.stageKey === "web_verification" && !webSearchEnabled && (
            <>
              <div className="h-px bg-slate-200 my-1" />
              <button
                className="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-emerald-700 hover:bg-emerald-50 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={(e) => {
                  e.stopPropagation()
                  onEnableWebSearchAndRelaunch()
                  setContextMenu(null)
                }}
                disabled={isRelaunching}
              >
                <Globe className="h-4 w-4" />
                <span>Enable Web Search & Relaunch</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function FactCard({ fact }: { fact: Fact }) {
  const [expanded, setExpanded] = React.useState(false)

  const getStatusColor = (status: string) => {
    switch (status) {
      case "verified": return "bg-emerald-50 text-emerald-700 border-emerald-200"
      case "debunked": return "bg-red-50 text-red-700 border-red-200"
      case "uncertain": return "bg-amber-50 text-amber-700 border-amber-200"
      default: return "bg-slate-50 text-slate-600 border-slate-200"
    }
  }

  const getStatusBgGradient = (status: string) => {
    switch (status) {
      case "verified": return "from-emerald-50/50 to-green-50/30"
      case "debunked": return "from-red-50/50 to-rose-50/30"
      case "uncertain": return "from-amber-50/50 to-yellow-50/30"
      default: return "from-slate-50/50 to-gray-50/30"
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "verified": return <CheckCircle2 className="h-4 w-4 text-emerald-600" />
      case "debunked": return <XCircle className="h-4 w-4 text-red-600" />
      case "uncertain": return <AlertCircle className="h-4 w-4 text-amber-600" />
      default: return <Clock className="h-4 w-4 text-slate-400" />
    }
  }

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return "bg-emerald-100 text-emerald-700 border-emerald-300"
    if (score >= 0.5) return "bg-amber-100 text-amber-700 border-amber-300"
    return "bg-red-100 text-red-700 border-red-300"
  }

  return (
    <Card className={`border border-slate-200 hover:border-indigo-300 hover:shadow-lg transition-all duration-200 overflow-hidden bg-gradient-to-br ${getStatusBgGradient(fact.verification_status)}`}>
      <button
        className="w-full flex items-start justify-between gap-3 p-4 text-left hover:bg-white/50 transition-colors cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="mt-0.5 flex-shrink-0">
            {getStatusIcon(fact.verification_status)}
          </div>
          <div className="text-sm text-slate-700 leading-relaxed flex-1">
            <MarkdownRenderer content={fact.content} />
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {fact.page_number && (
            <Badge variant="outline" className="text-xs bg-white border-slate-300 text-slate-600 px-2">
              Page {fact.page_number}
            </Badge>
          )}
          <Badge variant="outline" className={`text-xs font-medium ${getStatusColor(fact.verification_status)}`}>
            {fact.verification_status}
          </Badge>
          <Badge variant="outline" className={`text-xs font-semibold border-2 ${getConfidenceColor(fact.confidence_score)}`}>
            {Math.round(fact.confidence_score * 100)}%
          </Badge>
          <div className="ml-1">
            {expanded ? (
              <ChevronDown className="h-5 w-5 text-slate-400" />
            ) : (
              <ChevronRight className="h-5 w-5 text-slate-400" />
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-0 space-y-3 border-t border-slate-200/50 bg-white/60 animate-fade-in">
          {fact.verification_reasoning && (
            <div className="pt-3">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="h-3.5 w-3.5 text-indigo-600" />
                <span className="text-xs font-semibold text-slate-700 uppercase tracking-wide">Reasoning</span>
              </div>
              <div className="text-sm text-slate-600 leading-relaxed pl-5">
                <MarkdownRenderer content={fact.verification_reasoning} />
              </div>
            </div>
          )}
          {fact.web_source_url && fact.web_source_url.length > 0 && (
            <div className="pt-2">
              <div className="flex items-center gap-2 mb-2">
                <Globe className="h-3.5 w-3.5 text-indigo-600" />
                <span className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
                  {fact.web_source_url.length === 1 ? 'Source' : 'Sources'}
                </span>
              </div>
              <div className="space-y-1.5 pl-5">
                {fact.web_source_url.map((url, idx) => (
                  <a
                    key={idx}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-xs text-indigo-600 hover:text-indigo-800 hover:underline break-all"
                  >
                    <ExternalLink className="h-3.5 w-3.5 flex-shrink-0" />
                    <span>{url}</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export default function DocumentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const documentId = params.id as string
  const queryClient = useQueryClient()
  const { page, pageSize, setPage } = usePagination(1, 10)
  const [selectedStatuses, setSelectedStatuses] = React.useState<string[]>([
    "verified",
    "uncertain",
    "debunked",
    "pending",
  ])

  const { data: document, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => documentsApi.get(documentId),
    refetchInterval: (query) => {
      const doc = query.state.data
      if (!doc) return false
      const isProcessing = doc.processing_state !== "completed" && doc.processing_state !== "failed"
      return isProcessing ? 2000 : false
    },
  })

  const { data: factsData, isLoading: isLoadingFacts } = useQuery({
    queryKey: ["document-facts", documentId, page, pageSize, selectedStatuses],
    queryFn: () => documentsApi.getFacts(documentId, page, pageSize, selectedStatuses),
    enabled: !!document,
  })

  const paginatedFacts = factsData?.data || []
  const factsPagination = factsData?.pagination

  // Use pagination total or fallback to document facts count
  const totalFacts = factsPagination?.totalItems ?? document?.facts?.length ?? 0

  const reprocessMutation = useMutation({
    mutationFn: () => documentsApi.reprocess(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] })
    },
  })

  const reprocessFromStageMutation = useMutation({
    mutationFn: ({ stage, enableWebSearch }: { stage: string; enableWebSearch?: boolean }) =>
      documentsApi.reprocessFromStage(documentId, stage, enableWebSearch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] })
    },
  })

  const enableWebSearchAndRelaunchMutation = useMutation({
    mutationFn: () => documentsApi.reprocessFromStage(documentId, "web_verification", true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => documentsApi.stop(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] })
    },
  })

  const handleDownload = async () => {
    try {
      const response = await documentsApi.download(documentId)

      // Create a blob URL and trigger download
      const blob = new Blob([response.data], { type: response.headers['content-type'] })
      const url = window.URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = url
      link.download = document?.filename || 'document'
      window.document.body.appendChild(link)
      link.click()
      window.document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Download failed:', error)
    }
  }

  const isProcessing = document
    ? document.processing_state !== "completed" && document.processing_state !== "failed"
    : false

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // Group facts by verification status (for summary only - using ALL facts from document)
  const factGroups = React.useMemo(() => {
    if (!document?.facts) return { verified: [], debunked: [], uncertain: [], pending: [] }
    return {
      verified: document.facts.filter((f) => f.verification_status === "verified"),
      debunked: document.facts.filter((f) => f.verification_status === "debunked"),
      uncertain: document.facts.filter((f) => f.verification_status === "uncertain"),
      pending: document.facts.filter((f) => f.verification_status === "pending"),
    }
  }, [document?.facts])

  const displayedFacts = paginatedFacts

  const toggleStatus = (status: string) => {
    setSelectedStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status]
    )
    // Reset to page 1 when filter changes
    setPage(1)
  }

  if (isLoading) {
    return (
      <div className="doc-loading">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        <p className="text-sm text-slate-500 mt-2">Loading document...</p>
      </div>
    )
  }

  if (!document) {
    return (
      <div className="doc-loading">
        <p className="text-sm text-slate-500">Document not found</p>
        <Button variant="outline" size="sm" onClick={() => router.back()} className="mt-4">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Go back
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50/30">
      <div className="doc-page">
        {/* Enhanced Header */}
        <div className="space-y-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.back()}
            className="doc-back-btn hover:bg-slate-100"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Documents</span>
          </Button>

          <Card className="border-none shadow-lg bg-gradient-to-r from-white to-indigo-50/50">
            <div className="p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-4 flex-1">
                  <div className="p-3 bg-indigo-100 rounded-xl">
                    <FileText className="h-8 w-8 text-indigo-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h1 className="text-2xl font-bold text-slate-900 mb-2 break-words">{document.filename}</h1>
                    <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-slate-400" />
                        <span>{formatFileSize(document.file_size)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-slate-400" />
                        <span className="font-mono text-xs">{document.mime_type}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-indigo-400" />
                        <span className="font-semibold text-indigo-600">{totalFacts} facts extracted</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5 text-slate-400" />
                        <span className="text-xs">{new Date(document.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDownload}
                    className="border-slate-200 text-slate-600 hover:bg-slate-50"
                  >
                    <Download className="h-4 w-4 mr-1.5" />
                    Download
                  </Button>
                  {isProcessing ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => stopMutation.mutate()}
                      disabled={stopMutation.isPending}
                      className="border-red-200 text-red-600 hover:bg-red-50"
                    >
                      <Square className="h-4 w-4 mr-1.5" />
                      Stop
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => reprocessMutation.mutate()}
                      disabled={reprocessMutation.isPending}
                      className="border-indigo-200 text-indigo-600 hover:bg-indigo-50"
                    >
                      <RotateCw className={`h-4 w-4 mr-1.5 ${reprocessMutation.isPending ? "animate-spin" : ""}`} />
                      Reprocess
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Pipeline Progress */}
        <Card className="border-none shadow-md">
          <PipelineProgress
            currentState={document.processing_state}
            webSearchEnabled={document.web_search_enabled}
            onRelaunchFromStage={(stage) => reprocessFromStageMutation.mutate({ stage })}
            onEnableWebSearchAndRelaunch={() => enableWebSearchAndRelaunchMutation.mutate()}
            isRelaunching={reprocessFromStageMutation.isPending || enableWebSearchAndRelaunchMutation.isPending}
          />
        </Card>

        {/* Facts Section */}
        <Card className="border-none shadow-md">
          <div className="p-6">
            <div className="space-y-4 mb-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                    <AlertCircle className="h-5 w-5 text-indigo-600" />
                    Extracted Facts
                    <span className="text-slate-400">({totalFacts})</span>
                  </h3>
                  <p className="text-sm text-slate-500 mt-1">AI-verified information from the document</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {factGroups.verified.length > 0 && (
                    <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 px-3 py-1">
                      <CheckCircle2 className="h-3 w-3 mr-1" />
                      {factGroups.verified.length} verified
                    </Badge>
                  )}
                  {factGroups.debunked.length > 0 && (
                    <Badge className="bg-red-100 text-red-700 border-red-200 px-3 py-1">
                      <XCircle className="h-3 w-3 mr-1" />
                      {factGroups.debunked.length} debunked
                    </Badge>
                  )}
                  {factGroups.uncertain.length > 0 && (
                    <Badge className="bg-amber-100 text-amber-700 border-amber-200 px-3 py-1">
                      <AlertCircle className="h-3 w-3 mr-1" />
                      {factGroups.uncertain.length} uncertain
                    </Badge>
                  )}
                  {factGroups.pending.length > 0 && (
                    <Badge className="bg-slate-100 text-slate-600 border-slate-200 px-3 py-1">
                      <Clock className="h-3 w-3 mr-1" />
                      {factGroups.pending.length} pending
                    </Badge>
                  )}
                </div>
              </div>

              {/* Filter Chips */}
              <div className="flex items-center gap-3 pb-4 border-b border-slate-200">
                <span className="text-sm font-medium text-slate-600">Filter:</span>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => toggleStatus("verified")}
                    className={`filter-chip ${
                      selectedStatuses.includes("verified")
                        ? "bg-emerald-100 text-emerald-700 border-emerald-300 ring-2 ring-emerald-200"
                        : "bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200"
                    } px-3 py-1.5 rounded-full text-xs font-medium border transition-all flex items-center gap-1.5`}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Verified
                  </button>
                  <button
                    onClick={() => toggleStatus("uncertain")}
                    className={`filter-chip ${
                      selectedStatuses.includes("uncertain")
                        ? "bg-amber-100 text-amber-700 border-amber-300 ring-2 ring-amber-200"
                        : "bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200"
                    } px-3 py-1.5 rounded-full text-xs font-medium border transition-all flex items-center gap-1.5`}
                  >
                    <AlertCircle className="h-3.5 w-3.5" />
                    Uncertain
                  </button>
                  <button
                    onClick={() => toggleStatus("debunked")}
                    className={`filter-chip ${
                      selectedStatuses.includes("debunked")
                        ? "bg-red-100 text-red-700 border-red-300 ring-2 ring-red-200"
                        : "bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200"
                    } px-3 py-1.5 rounded-full text-xs font-medium border transition-all flex items-center gap-1.5`}
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Debunked
                  </button>
                  <button
                    onClick={() => toggleStatus("pending")}
                    className={`filter-chip ${
                      selectedStatuses.includes("pending")
                        ? "bg-slate-200 text-slate-700 border-slate-300 ring-2 ring-slate-200"
                        : "bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200"
                    } px-3 py-1.5 rounded-full text-xs font-medium border transition-all flex items-center gap-1.5`}
                  >
                    <Clock className="h-3.5 w-3.5" />
                    Pending
                  </button>
                </div>
              </div>
            </div>

            {selectedStatuses.length === 0 ? (
              <div className="doc-empty-facts bg-gradient-to-br from-slate-50 to-indigo-50/30 rounded-xl py-16">
                <AlertCircle className="h-12 w-12 text-slate-400 mb-4" />
                <p className="text-base font-medium text-slate-700">Select at least one filter to view facts</p>
                <p className="text-sm text-slate-500 mt-2">Choose from the filters above</p>
              </div>
            ) : isLoadingFacts ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
              </div>
            ) : totalFacts === 0 && document?.facts?.length === 0 ? (
              <div className="doc-empty-facts bg-gradient-to-br from-slate-50 to-indigo-50/30 rounded-xl py-16">
                {isProcessing ? (
                  <>
                    <Loader2 className="h-12 w-12 animate-spin text-indigo-500 mb-4" />
                    <p className="text-base font-medium text-slate-700">Extracting facts from document...</p>
                    <p className="text-sm text-slate-500 mt-2">This may take a moment</p>
                  </>
                ) : document.processing_state === "failed" ? (
                  <>
                    <XCircle className="h-12 w-12 text-red-500 mb-4" />
                    <p className="text-base font-medium text-slate-700">Processing failed</p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => reprocessMutation.mutate()}
                      className="mt-4 border-indigo-200 text-indigo-600 hover:bg-indigo-50"
                    >
                      <RotateCw className="h-4 w-4 mr-1.5" />
                      Try again
                    </Button>
                  </>
                ) : (
                  <>
                    <FileText className="h-12 w-12 text-slate-300 mb-4" />
                    <p className="text-base font-medium text-slate-700">No facts extracted yet</p>
                  </>
                )}
              </div>
            ) : displayedFacts.length === 0 ? (
              <div className="doc-empty-facts bg-gradient-to-br from-slate-50 to-indigo-50/30 rounded-xl py-16">
                <AlertCircle className="h-12 w-12 text-amber-500 mb-4" />
                <p className="text-base font-medium text-slate-700">No facts match the selected filters</p>
                <p className="text-sm text-slate-500 mt-2">Try adjusting your filter selection</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedStatuses(["verified", "uncertain", "debunked", "pending"])}
                  className="mt-4 border-indigo-200 text-indigo-600 hover:bg-indigo-50"
                >
                  Clear Filters
                </Button>
              </div>
            ) : (
              <>
                <div className="space-y-3">
                  {displayedFacts.map((fact, index) => (
                    <div key={fact.id} className="animate-fade-in-up" style={{ animationDelay: `${index * 50}ms` }}>
                      <FactCard fact={fact} />
                    </div>
                  ))}
                </div>

                {factsPagination && factsPagination.totalPages > 1 && (
                  <div className="mt-6 pt-6 border-t border-slate-200">
                    <Pagination
                      pagination={factsPagination}
                      onPageChange={setPage}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </Card>

        {/* Extracted Content Preview */}
        {document.extracted_content && (
          <Card className="border-none shadow-md">
            <div className="p-6">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2 mb-4">
                <FileText className="h-5 w-5 text-indigo-600" />
                Document Content
              </h3>
              <div className="prose prose-sm max-w-none bg-slate-50 rounded-lg p-4 border border-slate-200">
                <div className="text-sm text-slate-700 whitespace-pre-wrap max-h-96 overflow-y-auto leading-relaxed">
                  <MarkdownRenderer content={document.extracted_content.slice(0, 2000) + (document.extracted_content.length > 2000 ? '...' : '')} />
                </div>
                {document.extracted_content.length > 2000 && (
                  <div className="mt-4 text-xs text-slate-500 text-center">
                    Showing first 2000 characters. Full content available in the document.
                  </div>
                )}
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
