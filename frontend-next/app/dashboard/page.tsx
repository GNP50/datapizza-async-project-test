"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { ArrowRight, MessageSquare, FileText, TrendingUp, Plus, Loader2, Search, Trash2, Clock, Calendar, Activity } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { AlertDialog } from "@/components/ui/alert-dialog"
import { chatsApi } from "@/lib/api"
import { useState, useEffect, useMemo } from "react"
import { useDebounce } from "@/hooks/use-debounce"
import { useToast } from "@/lib/toast-context"
import React from "react"

export default function DashboardPage() {
  const [searchQuery, setSearchQuery] = useState("")
  const debouncedSearch = useDebounce(searchQuery, 300)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [chatToDelete, setChatToDelete] = useState<{ id: string; title: string } | null>(null)
  const queryClient = useQueryClient()
  const { addToast } = useToast()

  const { data: chats, isLoading } = useQuery({
    queryKey: ['chats'],
    queryFn: () => chatsApi.list()
  })

  // Calculate enhanced statistics from chats data
  const stats = React.useMemo(() => {
    if (!chats?.data) return {
      totalChats: 0,
      totalMessages: 0,
      activeChats: 0,
      recentChats: 0,
      todayChats: 0,
      thisWeekChats: 0,
      avgChatsPerDay: 0
    }

    const now = new Date()
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

    const todayChats = chats.data.filter(chat =>
      new Date(chat.updated_at) >= todayStart
    ).length

    const thisWeekChats = chats.data.filter(chat =>
      new Date(chat.updated_at) > oneWeekAgo
    ).length

    // Calculate average chats per day (last 7 days)
    const avgChatsPerDay = thisWeekChats > 0 ? (thisWeekChats / 7).toFixed(1) : 0

    return {
      totalChats: chats.data.length,
      totalMessages: 0, // This would need to be fetched from backend
      activeChats: thisWeekChats,
      recentChats: thisWeekChats,
      todayChats,
      thisWeekChats,
      avgChatsPerDay
    }
  }, [chats])

  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ['chats', 'search', debouncedSearch],
    queryFn: () => chatsApi.search(debouncedSearch),
    enabled: debouncedSearch.length > 0
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

  const displayChats = debouncedSearch.length > 0
    ? (searchResults?.data?.map(r => r.chat) || [])
    : (chats?.data || [])

  const recentChats = Array.isArray(displayChats) ? displayChats.slice(0, 3) : []

  return (
    <div className="container mx-auto px-4 py-8 animate-fade-in-up">
      <div className="mb-8 flex items-center justify-between animate-fade-in-down">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Welcome back! Here&apos;s your activity overview.</p>
        </div>
        <Button asChild size="lg" className="group relative overflow-hidden">
          <Link href="/chats/new" className="flex items-center gap-2">
            <div className="absolute inset-0 bg-gradient-to-r from-primary/20 to-accent/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            <Plus className="h-5 w-5 group-hover:rotate-90 transition-transform duration-300" />
            <span className="relative">New Chat</span>
          </Link>
        </Button>
      </div>

      <div className="mb-8 grid gap-6 md:grid-cols-3">
        <Card className="hover-lift animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardDescription>Total Chats</CardDescription>
            <MessageSquare className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-foreground">
              {isLoading ? <Loader2 className="h-8 w-8 animate-spin" /> : stats.totalChats}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              All conversations
            </p>
          </CardContent>
        </Card>

        <Card className="hover-lift animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardDescription>Active This Week</CardDescription>
            <TrendingUp className="h-4 w-4 text-success" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-foreground">
              {isLoading ? <Loader2 className="h-8 w-8 animate-spin" /> : stats.activeChats}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {stats.activeChats > 0 ? `${((stats.activeChats / stats.totalChats) * 100).toFixed(0)}% of total` : 'No recent activity'}
            </p>
          </CardContent>
        </Card>

        <Card className="hover-lift animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardDescription>Recent Activity</CardDescription>
            <FileText className="h-4 w-4 text-accent" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-foreground">
              {isLoading ? <Loader2 className="h-8 w-8 animate-spin" /> : stats.recentChats}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Chats updated recently
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Activity Stats */}
      {!isLoading && chats?.data && chats.data.length > 0 && (
        <div className="mb-8 animate-fade-in-up" style={{ animationDelay: "0.35s" }}>
          <Card className="border-accent/20 bg-gradient-to-r from-accent/5 via-primary/5 to-accent/5">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5 text-accent" />
                    Activity Summary
                  </CardTitle>
                  <CardDescription className="mt-1">
                    Your chat activity overview
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4">
                <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-card border border-border">
                  <Clock className="h-5 w-5 text-blue-500 mb-2" />
                  <div className="text-2xl font-bold text-foreground">{stats.todayChats}</div>
                  <p className="text-xs text-muted-foreground mt-1">Today</p>
                </div>
                <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-card border border-border">
                  <Calendar className="h-5 w-5 text-green-500 mb-2" />
                  <div className="text-2xl font-bold text-foreground">{stats.thisWeekChats}</div>
                  <p className="text-xs text-muted-foreground mt-1">This Week</p>
                </div>
                <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-card border border-border">
                  <TrendingUp className="h-5 w-5 text-purple-500 mb-2" />
                  <div className="text-2xl font-bold text-foreground">{stats.avgChatsPerDay}</div>
                  <p className="text-xs text-muted-foreground mt-1">Avg/Day</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="animate-fade-in-left">
          <div className="mb-4 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-foreground">Recent Chats</h2>
              <Button variant="ghost" size="sm" asChild className="hover-scale">
                <Link href="/chats">
                  View All
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search chats..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          {(isLoading || isSearching) ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : recentChats.length === 0 ? (
            <Card className="glass">
              <CardHeader>
                <CardDescription className="text-center py-8">
                  {debouncedSearch.length > 0
                    ? "No chats found matching your search."
                    : "No chats yet. Create your first chat to get started!"}
                </CardDescription>
              </CardHeader>
            </Card>
          ) : (
            <div className="space-y-3">
              {recentChats.map((chat, index) => {
                const updatedAt = new Date(chat.updated_at)
                const createdAt = new Date(chat.created_at)
                const isNew = updatedAt.getTime() - createdAt.getTime() < 60000 // Less than 1 minute old
                const timeSinceUpdate = Date.now() - updatedAt.getTime()
                const isRecent = timeSinceUpdate < 3600000 // Less than 1 hour

                return (
                  <div key={chat.id} className="relative group">
                    <Link href={`/chats/${chat.id}`}>
                      <Card className="cursor-pointer hover-lift animate-fade-in-up" style={{ animationDelay: `${0.1 * index}s` }}>
                        <CardHeader>
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <CardTitle className="text-lg">{chat.title}</CardTitle>
                                {isNew && (
                                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                                    New
                                  </Badge>
                                )}
                                {isRecent && !isNew && (
                                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 border-green-300 text-green-700">
                                    Active
                                  </Badge>
                                )}
                              </div>
                              <CardDescription className="mt-1 flex items-center gap-2">
                                <span>{new Date(chat.updated_at).toLocaleString()}</span>
                                {chat.summary && (
                                  <span className="text-xs text-slate-400 truncate max-w-[200px]">
                                    • {chat.summary}
                                  </span>
                                )}
                              </CardDescription>
                            </div>
                            <ArrowRight className="h-5 w-5 text-muted-foreground opacity-0 transition-all duration-200 group-hover:opacity-100 group-hover:translate-x-1" />
                          </div>
                        </CardHeader>
                      </Card>
                    </Link>

                    {/* Delete button - appears on hover */}
                    <Button
                      variant="destructive"
                      size="icon"
                      className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 shadow-lg z-10"
                      onClick={(e) => handleDeleteClick(e, chat.id, chat.title)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="animate-fade-in-right">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-bold text-foreground">Quick Actions</h2>
          </div>

          <div className="space-y-3">
            <Link href="/chats/new">
              <Card className="group cursor-pointer border-primary/20 bg-gradient-to-br from-primary/5 to-accent/5 hover-lift animate-fade-in-up">
                <CardHeader>
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg group-hover:scale-110 transition-transform duration-200">
                      <MessageSquare className="h-6 w-6" />
                    </div>
                    <div>
                      <CardTitle className="text-base">Start New Chat</CardTitle>
                      <CardDescription>Begin a conversation with AI</CardDescription>
                    </div>
                  </div>
                </CardHeader>
              </Card>
            </Link>

            <Card className="group cursor-pointer border-muted bg-gradient-to-br from-muted/30 to-muted/10 opacity-50 animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
              <CardHeader>
                <div className="flex items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted-foreground text-white shadow-lg">
                    <FileText className="h-6 w-6" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Upload Document</CardTitle>
                    <CardDescription>Coming soon</CardDescription>
                  </div>
                </div>
              </CardHeader>
            </Card>
          </div>
        </div>
      </div>

      <div className="mt-8 animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
        <Card className="border-primary/20 bg-gradient-to-r from-primary/5 via-accent/5 to-primary/5 hover-lift">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <Badge variant="secondary" className="mb-2 animate-pulse">
                  Pro Tip
                </Badge>
                <CardTitle>Use Cmd+K for quick navigation</CardTitle>
                <CardDescription className="mt-1">
                  Access the command palette anywhere in the app for faster workflows
                </CardDescription>
              </div>
              <kbd className="hidden md:inline-flex h-8 select-none items-center gap-1 rounded-md border border-border bg-card px-2 font-mono text-sm font-medium text-foreground shadow-sm">
                <span className="text-xs">⌘</span>K
              </kbd>
            </div>
          </CardHeader>
        </Card>
      </div>

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
