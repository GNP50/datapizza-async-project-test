"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { MessageSquare, Plus, Clock, Loader2, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Pagination } from "@/components/ui/pagination"
import { AlertDialog } from "@/components/ui/alert-dialog"
import { chatsApi } from "@/lib/api"
import { usePagination } from "@/lib/usePagination"
import { useToast } from "@/lib/toast-context"

export default function ChatsPage() {
  const { page, pageSize, setPage } = usePagination(1, 12)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState<{ id: string; title: string } | null>(null)
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const { data, isLoading } = useQuery({
    queryKey: ['chats', page, pageSize],
    queryFn: () => chatsApi.list(page, pageSize)
  })

  const deleteMutation = useMutation({
    mutationFn: (chatId: string) => chatsApi.delete(chatId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      addToast("Chat deleted successfully. All associated data has been removed.", "success")
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

  const handleDeleteClick = (e: React.MouseEvent, chatId: string, chatTitle: string) => {
    e.preventDefault()
    e.stopPropagation()
    setChatToDelete({ id: chatId, title: chatTitle })
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = () => {
    if (chatToDelete) {
      deleteMutation.mutate(chatToDelete.id)
      setChatToDelete(null)
    }
  }

  const chats = data?.data
  const paginationInfo = data?.pagination

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">All Chats</h1>
          <p className="mt-1 text-slate-500">Manage and view your conversation history</p>
        </div>
        <Button asChild size="lg" className="group relative overflow-hidden">
          <Link href="/chats/new">
            <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <Plus className="h-5 w-5 group-hover:rotate-90 transition-transform duration-300" />
            <span className="relative">New Chat</span>
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-12 w-12 animate-spin text-indigo-600" />
        </div>
      ) : chats && chats.length > 0 ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {chats.map((chat) => (
              <div key={chat.id} className="relative group">
                <Link href={`/chats/${chat.id}`}>
                  <Card className="h-full cursor-pointer transition-all hover:shadow-md">
                    <CardHeader>
                      <div className="mb-3 flex items-start justify-between">
                        <MessageSquare className="h-5 w-5 text-indigo-600" />
                        <div className="flex items-center gap-1 text-xs text-slate-500">
                          <Clock className="h-3 w-3" />
                          {new Date(chat.updated_at).toLocaleDateString()}
                        </div>
                      </div>

                      <CardTitle className="line-clamp-2 group-hover:text-indigo-600 transition-colors">
                        {chat.title}
                      </CardTitle>

                      <CardDescription className="mt-2">
                        Created {new Date(chat.created_at).toLocaleString()}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </Link>

                {/* Delete button - appears on hover */}
                <Button
                  variant="destructive"
                  size="icon"
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 shadow-lg"
                  onClick={(e) => handleDeleteClick(e, chat.id, chat.title)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          {paginationInfo && paginationInfo.totalPages > 1 && (
            <Pagination
              pagination={paginationInfo}
              onPageChange={setPage}
            />
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center py-16">
          <MessageSquare className="h-16 w-16 text-slate-300 mb-4" />
          <h3 className="text-xl font-semibold text-slate-900 mb-2">No chats yet</h3>
          <p className="text-slate-500 mb-6">Start your first conversation with AI</p>
          <Button asChild size="lg" className="group relative overflow-hidden">
            <Link href="/chats/new">
              <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <Plus className="h-5 w-5 group-hover:rotate-90 transition-transform duration-300" />
              <span className="relative">Create New Chat</span>
            </Link>
          </Button>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Delete Chat"
        description={`Are you sure you want to delete "${chatToDelete?.title}"? This will permanently remove the chat and all associated messages, documents, facts, and flashcards. This action cannot be undone.`}
        actionLabel="Delete"
        cancelLabel="Cancel"
        variant="destructive"
        onAction={handleDeleteConfirm}
      />
    </div>
  )
}
