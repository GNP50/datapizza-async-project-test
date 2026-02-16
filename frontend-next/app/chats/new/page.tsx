"use client"

import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { MessageSquare, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { chatsApi } from "@/lib/api"

export default function NewChatPage() {
  const router = useRouter()
  const [title, setTitle] = React.useState("")

  const createChatMutation = useMutation({
    mutationFn: (title: string) => chatsApi.create(title),
    onSuccess: (newChat) => {
      router.push(`/chats/${newChat.id}`)
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    createChatMutation.mutate(title)
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-100">
            <MessageSquare className="h-8 w-8 text-indigo-600" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900">Start New Chat</h1>
          <p className="mt-2 text-slate-500">
            Create a new conversation with AI assistant
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Chat Details</CardTitle>
            <CardDescription>
              Give your chat a descriptive title to help you find it later
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <label htmlFor="title" className="text-sm font-medium text-slate-900">
                  Chat Title
                </label>
                <input
                  id="title"
                  type="text"
                  placeholder="e.g., Product Analysis, Market Research..."
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  disabled={createChatMutation.isPending}
                  className="flex h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-sm ring-offset-white placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-600 focus-visible:ring-offset-2 disabled:opacity-50"
                />
              </div>

              <Button
                type="submit"
                className="w-full"
                disabled={!title.trim() || createChatMutation.isPending}
              >
                {createChatMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  "Create Chat"
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="mt-8">
          <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50 to-violet-50">
            <CardHeader>
              <CardTitle className="text-base">💡 Pro Tips</CardTitle>
              <CardDescription className="space-y-1">
                <p>• Use descriptive titles to organize your conversations</p>
                <p>• You can always rename your chat later</p>
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </div>
    </div>
  )
}
