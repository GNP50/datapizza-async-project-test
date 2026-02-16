"use client"

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { useDebounce } from "@/hooks/useDebounce"
import { chatsApi, type SearchResult } from "@/lib/api"
import { Clock, FileText, LogOut, MessageSquare, Search, Settings, User } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

export function CommandPalette() {
  const router = useRouter()
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")
  const [searchResults, setSearchResults] = React.useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = React.useState(false)

  const debouncedSearch = useDebounce(search, 400)

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  // Semantic search when user types
  React.useEffect(() => {
    const performSearch = async () => {
      if (!debouncedSearch || debouncedSearch.trim().length < 2) {
        setSearchResults([])
        return
      }

      setIsSearching(true)
      try {
        const result = await chatsApi.search(debouncedSearch.trim(), undefined, 10)
        setSearchResults(result.data)
      } catch (error) {
        console.error("Search failed:", error)
        setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    }

    performSearch()
  }, [debouncedSearch])

  const runCommand = React.useCallback((command: () => void) => {
    setOpen(false)
    setSearch("")
    setSearchResults([])
    command()
  }, [])

  if (!open) return null

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return `${diffDays} days ago`
    return date.toLocaleDateString()
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/50 backdrop-blur-sm"
      onClick={() => {
        setOpen(false)
        setSearch("")
        setSearchResults([])
      }}
    >
      <div
        className="fixed left-1/2 top-[20%] w-full max-w-2xl -translate-x-1/2"
        onClick={(e) => e.stopPropagation()}
      >
        <Command className="rounded-xl border border-slate-200 shadow-2xl">
          <CommandInput
            placeholder="Search chats or type a command..."
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>
              {isSearching ? "Searching..." : "No results found."}
            </CommandEmpty>

            {/* Search Results */}
            {searchResults.length > 0 && (
              <>
                <CommandGroup heading="Search Results">
                  {searchResults.map((result) => (
                    <CommandItem
                      key={result.chat.id}
                      onSelect={() => runCommand(() => router.push(`/chats/${result.chat.id}`))}
                      className="flex flex-col items-start gap-1 py-3"
                    >
                      <div className="flex w-full items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Search className="h-4 w-4 text-slate-500" />
                          <span className="font-medium">{result.chat.title || "Untitled"}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5">
                            {Math.round(result.score * 100)}% match
                          </span>
                          <Clock className="h-3 w-3" />
                          <span>{formatDate(result.chat.created_at)}</span>
                        </div>
                      </div>
                      {result.chat.summary && (
                        <p className="ml-6 text-xs text-slate-500 line-clamp-1">
                          {result.chat.summary}
                        </p>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
                <CommandSeparator />
              </>
            )}

            {/* Navigation */}
            <CommandGroup heading="Navigation">
              <CommandItem
                onSelect={() => runCommand(() => router.push("/dashboard"))}
              >
                <MessageSquare className="mr-2 h-4 w-4" />
                <span>Dashboard</span>
              </CommandItem>
              <CommandItem
                onSelect={() => runCommand(() => router.push("/chats"))}
              >
                <MessageSquare className="mr-2 h-4 w-4" />
                <span>Chats</span>
              </CommandItem>
              <CommandItem
                onSelect={() => runCommand(() => router.push("/documents"))}
              >
                <FileText className="mr-2 h-4 w-4" />
                <span>Documents</span>
              </CommandItem>
            </CommandGroup>

            {/* Account */}
            <CommandGroup heading="Account">
              <CommandItem
                onSelect={() => runCommand(() => router.push("/settings"))}
              >
                <Settings className="mr-2 h-4 w-4" />
                <span>Settings</span>
              </CommandItem>
              <CommandItem
                onSelect={() => runCommand(() => router.push("/profile"))}
              >
                <User className="mr-2 h-4 w-4" />
                <span>Profile</span>
              </CommandItem>
              <CommandItem
                onSelect={() => runCommand(() => router.push("/logout"))}
              >
                <LogOut className="mr-2 h-4 w-4" />
                <span>Logout</span>
              </CommandItem>
            </CommandGroup>
          </CommandList>
        </Command>
      </div>
    </div>
  )
}
