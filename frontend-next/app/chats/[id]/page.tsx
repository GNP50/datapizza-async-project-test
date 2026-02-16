"use client"

import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams, useRouter } from "next/navigation"
import { Send, Bot, Paperclip, Loader2, X, PanelRightOpen, FileCheck2, Trash2, MoreVertical, MessageSquare, Zap, Database, CheckCircle2, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { chatsApi, messagesApi, documentsApi } from "@/lib/api"
import { ChatLayout } from "@/components/chat/ChatLayout"
import { MessageBubble } from "@/components/chat/MessageBubble"
import { UploadConfirmationDialog } from "@/components/upload-confirmation-dialog"
import { AlertDialog } from "@/components/ui/alert-dialog"
import { useToast } from "@/lib/toast-context"

export default function ChatPage() {
  const params = useParams()
  const chatId = params.id as string
  const router = useRouter()
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [input, setInput] = React.useState("")
  const [selectedFiles, setSelectedFiles] = React.useState<File[]>([])
  const [webSearchSettings, setWebSearchSettings] = React.useState<boolean[]>([])
  const [showUploadDialog, setShowUploadDialog] = React.useState(false)
  const [pendingFiles, setPendingFiles] = React.useState<File[]>([])
  const [sidebarOpen, setSidebarOpen] = React.useState(false)
  const [highlightedMessageId, setHighlightedMessageId] = React.useState<string | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const messagesEndRef = React.useRef<HTMLDivElement>(null)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  const { data: chat } = useQuery({
    queryKey: ['chat', chatId],
    queryFn: () => chatsApi.get(chatId)
  })

  const { data: messagesResult, isLoading } = useQuery({
    queryKey: ['messages', chatId],
    queryFn: () => messagesApi.list(chatId),
    refetchInterval: (query) => {
      const result = query.state.data
      if (!result?.data) return false

      // Check for pending messages
      const hasPendingMessages = result.data.some(
        (m) => m.processing_state !== 'completed' && m.processing_state !== 'failed'
      )

      // Check for pending documents
      const hasPendingDocuments = result.data.some((m) =>
        m.documents?.some((d) =>
          d.processing_state !== 'completed' && d.processing_state !== 'failed'
        )
      )

      return (hasPendingMessages || hasPendingDocuments) ? 2000 : false
    }
  })

  const messages = messagesResult?.data || []

  const sendMessageMutation = useMutation({
    mutationFn: (data: { content: string, files: File[], webSearchSettings?: boolean[] }) => {
      if (data.files.length > 0) {
        return messagesApi.sendWithFiles(chatId, data.content, data.files, data.webSearchSettings)
      }
      return messagesApi.send(chatId, data.content)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
      setInput("")
      setSelectedFiles([])
      setWebSearchSettings([])
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if ((input.trim() === "" && selectedFiles.length === 0) || sendMessageMutation.isPending) return
    sendMessageMutation.mutate({ content: input, files: selectedFiles, webSearchSettings })
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files)

      // Define allowed MIME types for textual files
      const allowedMimeTypes = new Set([
        'application/pdf',
        'text/plain',
        'text/markdown',
        'text/x-markdown',
        'text/x-python',
        'text/x-java-source',
        'text/x-c',
        'text/x-c++',
        'text/javascript',
        'application/javascript',
        'text/x-java',
        'text/x-ruby',
        'text/x-go',
        'text/x-rust',
        'text/x-php',
        'text/html',
        'text/css',
        'application/json',
        'application/xml',
        'text/xml',
        'text/csv',
        'text/x-yaml',
        'application/x-yaml',
      ])

      // Filter for allowed file types (textual files and PDFs)
      const validFiles = files.filter(file => {
        // Check MIME type or if it starts with "text/"
        return allowedMimeTypes.has(file.type) || file.type.startsWith('text/')
      })

      if (validFiles.length !== files.length) {
        alert('Only textual files (PDF, TXT, MD, code files, etc.) are allowed')
        return
      }

      // Show upload dialog for file configuration
      setPendingFiles(validFiles)
      setShowUploadDialog(true)
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleUploadConfirm = (webSearchSettings: boolean[]) => {
    setSelectedFiles(pendingFiles)
    setWebSearchSettings(webSearchSettings)
    setShowUploadDialog(false)
    setPendingFiles([])
  }

  const handleUploadCancel = () => {
    setShowUploadDialog(false)
    setPendingFiles([])
  }

  const removeFile = (index: number) => {
    setSelectedFiles(files => files.filter((_, i) => i !== index))
    setWebSearchSettings(settings => settings.filter((_, i) => i !== index))
  }

  const handleVerifyClick = (messageId: string) => {
    setHighlightedMessageId(messageId)
    setSidebarOpen(true)
  }

  const handleClearFilter = () => {
    setHighlightedMessageId(null)
  }

  const retryMutation = useMutation({
    mutationFn: (messageId: string) => messagesApi.retry(chatId, messageId),
    onSuccess: async () => {
      // Force refetch to update UI immediately after cleanup
      await queryClient.refetchQueries({ queryKey: ['messages', chatId] })
    },
    onError: (error) => {
      console.error('Failed to retry message:', error)
      alert('Failed to retry message. Please try again.')
    }
  })

  const handleRetry = async (messageId: string) => {
    retryMutation.mutate(messageId)
  }

  const stopMutation = useMutation({
    mutationFn: (messageId: string) => messagesApi.stop(chatId, messageId),
    onSuccess: async () => {
      // Force refetch to update UI immediately after cleanup
      await queryClient.refetchQueries({ queryKey: ['messages', chatId] })
    },
    onError: (error) => {
      console.error('Failed to stop message processing:', error)
      alert('Failed to stop message processing. Please try again.')
    }
  })

  const handleStop = async (messageId: string) => {
    stopMutation.mutate(messageId)
  }

  const docReprocessMutation = useMutation({
    mutationFn: (documentId: string) => documentsApi.reprocess(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
    },
    onError: (error) => {
      console.error('Failed to reprocess document:', error)
    }
  })

  const docStopMutation = useMutation({
    mutationFn: (documentId: string) => documentsApi.stop(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
    },
    onError: (error) => {
      console.error('Failed to stop document:', error)
    }
  })

  const generateFlashcardsMutation = useMutation({
    mutationFn: (documentId: string) => documentsApi.generateFlashcards(documentId),
    onSuccess: () => {
      alert('Flashcard generation started! Check the document details page to view them once ready.')
    },
    onError: (error) => {
      console.error('Failed to generate flashcards:', error)
      alert('Failed to generate flashcards. Make sure the document is fully processed.')
    }
  })

  const bypassCacheMutation = useMutation({
    mutationFn: (messageId: string) => messagesApi.regenerateWithoutCache(chatId, messageId),
    onSuccess: async () => {
      // Force refetch to update UI immediately after cleanup
      await queryClient.refetchQueries({ queryKey: ['messages', chatId] })
    },
    onError: (error) => {
      console.error('Failed to regenerate without cache:', error)
      alert('Failed to regenerate response. Please try again.')
    }
  })

  const deleteChatMutation = useMutation({
    mutationFn: () => chatsApi.delete(chatId),
    onSuccess: () => {
      addToast("Chat deleted successfully. All associated data has been removed.", "success")
      router.push('/chats')
    },
    onError: (error: unknown) => {
      const errorMessage = error && typeof error === 'object' && 'response' in error
        ? (error.response as { data?: { detail?: string } })?.data?.detail
        : undefined
      addToast(
        errorMessage || "Failed to delete chat. Please try again.",
        "error"
      )
    }
  })

  const handleBypassCache = async (messageId: string) => {
    bypassCacheMutation.mutate(messageId)
  }

  const handleDeleteChat = () => {
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = () => {
    deleteChatMutation.mutate()
  }

  // Count documents across all messages
  const totalDocuments = React.useMemo(() => {
    if (!messages.length) return 0
    const docsMap = new Map()
    messages.forEach(msg => {
      msg.documents?.forEach(doc => docsMap.set(doc.id, doc))
    })
    return docsMap.size
  }, [messages])

  // Chat statistics
  const chatStats = React.useMemo(() => {
    if (!messages.length) return {
      totalMessages: 0,
      userMessages: 0,
      assistantMessages: 0,
      totalFactChecks: 0,
      cachedResponses: 0,
      ragResponses: 0,
      completedDocs: 0,
      processingDocs: 0
    }

    const docsMap = new Map()
    let totalFactChecks = 0
    let cachedResponses = 0
    let ragResponses = 0

    messages.forEach(msg => {
      // Count fact checks
      if (msg.fact_checks?.length > 0) {
        totalFactChecks += msg.fact_checks.length
      }

      // Count cache hits and RAG responses
      const responseType = msg.response_type || msg.response_metadata?.response_type
      if (msg.response_cached || msg.response_metadata?.cached || responseType === "cached") {
        cachedResponses++
      } else if (responseType === "rag") {
        ragResponses++
      }

      // Track documents
      msg.documents?.forEach(doc => docsMap.set(doc.id, doc))
    })

    const docs = Array.from(docsMap.values())
    const completedDocs = docs.filter(d => d.processing_state === 'completed').length
    const processingDocs = docs.filter(d => d.processing_state !== 'completed' && d.processing_state !== 'failed').length

    return {
      totalMessages: messages.length,
      userMessages: messages.filter(m => m.role === 'user').length,
      assistantMessages: messages.filter(m => m.role === 'assistant').length,
      totalFactChecks,
      cachedResponses,
      ragResponses,
      completedDocs,
      processingDocs
    }
  }, [messages])

  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <>
      {/* Upload Confirmation Dialog */}
      {showUploadDialog && (
        <UploadConfirmationDialog
          files={pendingFiles}
          onConfirm={handleUploadConfirm}
          onCancel={handleUploadCancel}
        />
      )}

      <ChatLayout
      messages={messages}
      sidebarOpen={sidebarOpen}
      onSidebarToggle={setSidebarOpen}
      highlightedMessageId={highlightedMessageId}
      onClearFilter={handleClearFilter}
      onDocumentReprocess={(docId) => docReprocessMutation.mutate(docId)}
      onDocumentStop={(docId) => docStopMutation.mutate(docId)}
      onGenerateFlashcards={(docId) => generateFlashcardsMutation.mutate(docId)}
    >
      <div className="chat-container">
        <div className="chat-header">
          <div className="chat-header-content">
            <div className="flex-1">
              <h1 className="chat-title">
                {chat?.title || 'Loading...'}
              </h1>
              <div className="flex items-center gap-3 mt-2 flex-wrap">
                <Badge variant="secondary" className="flex items-center gap-1">
                  <MessageSquare className="h-3 w-3" />
                  {chatStats.totalMessages} messages
                </Badge>

                {totalDocuments > 0 && (
                  <Badge variant="outline" className="flex items-center gap-1">
                    <FileCheck2 className="h-3 w-3" />
                    {chatStats.completedDocs}/{totalDocuments} docs
                    {chatStats.processingDocs > 0 && (
                      <Clock className="h-3 w-3 ml-1 text-blue-500 animate-pulse" />
                    )}
                  </Badge>
                )}

                {chatStats.totalFactChecks > 0 && (
                  <Badge variant="outline" className="flex items-center gap-1 text-green-600 border-green-300">
                    <CheckCircle2 className="h-3 w-3" />
                    {chatStats.totalFactChecks} facts
                  </Badge>
                )}

                {chatStats.cachedResponses > 0 && (
                  <Badge variant="outline" className="flex items-center gap-1 text-blue-600 border-blue-300">
                    <Zap className="h-3 w-3" />
                    {chatStats.cachedResponses} cached
                  </Badge>
                )}

                {chatStats.ragResponses > 0 && (
                  <Badge variant="outline" className="flex items-center gap-1 text-purple-600 border-purple-300">
                    <Database className="h-3 w-3" />
                    {chatStats.ragResponses} RAG
                  </Badge>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Sidebar Toggle Button */}
              {totalDocuments > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="chat-sidebar-toggle"
                >
                  <FileCheck2 className="h-4 w-4 mr-2" />
                  <span>Documents ({totalDocuments})</span>
                  <PanelRightOpen className={`h-4 w-4 ml-2 transition-transform ${sidebarOpen ? 'rotate-180' : ''}`} />
                </Button>
              )}

              {/* Delete Chat Button */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDeleteChat}
                disabled={deleteChatMutation.isPending}
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <div className="chat-messages-container">
          <div className="chat-messages-wrapper">
            {isLoading ? (
              <div className="loading-spinner-container">
                <Loader2 className="loading-spinner" />
              </div>
            ) : messages && messages.length > 0 ? (
              messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onVerifyClick={() => handleVerifyClick(message.id)}
                  onRetry={() => handleRetry(message.id)}
                  onStop={() => handleStop(message.id)}
                  onBypassCache={() => handleBypassCache(message.id)}
                  onDocumentReprocess={(docId) => docReprocessMutation.mutate(docId)}
                  onDocumentStop={(docId) => docStopMutation.mutate(docId)}
                  onGenerateFlashcards={(docId) => generateFlashcardsMutation.mutate(docId)}
                />
              ))
            ) : (
              <div className="empty-state">
                <Bot className="empty-state-icon" />
                <h3 className="empty-state-title">
                  Start the conversation
                </h3>
                <p className="empty-state-description">
                  Send a message or attach documents (PDF, TXT, MD, code files) to begin chatting with AI
                </p>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="chat-input-container">
          <form onSubmit={handleSubmit} className="chat-input-wrapper">
            {selectedFiles.length > 0 && (
              <div className="file-attachments-container">
                {selectedFiles.map((file, index) => (
                  <div
                    key={index}
                    className="file-attachment-chip"
                  >
                    <Paperclip className="h-3 w-3 text-slate-500" />
                    <span className="file-attachment-name">{file.name}</span>
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="file-attachment-remove"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="chat-input-controls">
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                multiple={true}
                className="hidden"
                accept=".pdf,.txt,.md,.java,.py,.js,.jsx,.ts,.tsx,.c,.cpp,.h,.hpp,.cs,.rb,.go,.rs,.php,.html,.css,.json,.xml,.csv,.yaml,.yml"
                aria-label="Upload textual files"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="btn-attachment"
                onClick={() => fileInputRef.current?.click()}
                disabled={sendMessageMutation.isPending}
              >
                <Paperclip className="h-4 w-4" />
              </Button>

              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your message or attach documents..."
                disabled={sendMessageMutation.isPending}
                className="chat-input-field"
              />

              <Button
                type="submit"
                size="icon"
                className="btn-send"
                disabled={(input.trim() === "" && selectedFiles.length === 0) || sendMessageMutation.isPending}
              >
                {sendMessageMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>

            <p className="mt-2 text-center text-xs text-slate-500">
              Press <kbd className="kbd">Enter</kbd>{" "}
              to send • Attach documents (PDF, TXT, MD, code files) for fact-checked responses
            </p>
          </form>
        </div>
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete Chat"
        description={`Are you sure you want to delete "${chat?.title}"? This will permanently remove the chat and all associated messages, documents, facts, and flashcards. This action cannot be undone.`}
        actionLabel="Delete"
        cancelLabel="Cancel"
        variant="destructive"
        onAction={handleDeleteConfirm}
      />
    </ChatLayout>
    </>
  )
}
