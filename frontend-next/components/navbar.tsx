"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Search, User, LogOut, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { isAuthenticated, logout } from "@/lib/auth"
import { PizzaIcon } from "@/components/pizza-icon"

const PUBLIC_ROUTES = ['/', '/login', '/register']

export function Navbar() {
  const pathname = usePathname()
  const [isScrolled, setIsScrolled] = React.useState(false)
  const [isAuthed, setIsAuthed] = React.useState(false)

  React.useEffect(() => {
    setIsAuthed(isAuthenticated())
    
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10)
    }
    window.addEventListener("scroll", handleScroll)
    return () => window.removeEventListener("scroll", handleScroll)
  }, [pathname])

  const isPublicRoute = PUBLIC_ROUTES.includes(pathname)
  const showAuthNavbar = isAuthed && !isPublicRoute

  return (
    <header
      className={cn(
        "sticky top-0 z-50 w-full border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/60 transition-all duration-300",
        isScrolled && "shadow-lg"
      )}
    >
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link href={isAuthed ? "/dashboard" : "/"} className="flex items-center gap-2 hover-scale">
            <PizzaIcon className="h-6 w-6" />
            <span className="text-xl font-bold gradient-text">AiFactChecker</span>
          </Link>
          
          {showAuthNavbar && (
            <nav className="hidden md:flex items-center gap-6">
              <Link
                href="/dashboard"
                className={cn(
                  "text-sm font-medium transition-all duration-200 hover:scale-105",
                  pathname === "/dashboard"
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Dashboard
              </Link>
              <Link
                href="/chats"
                className={cn(
                  "text-sm font-medium transition-all duration-200 hover:scale-105",
                  pathname.startsWith("/chats")
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                Chats
              </Link>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-3">
          {showAuthNavbar ? (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="hidden md:inline-flex"
                aria-label="Search"
              >
                <Search className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="icon"
                aria-label="Settings"
                className="hover-scale"
                asChild
              >
                <Link href="/settings">
                  <Settings className="h-4 w-4" />
                </Link>
              </Button>

              <Button
                variant="ghost"
                size="icon"
                aria-label="Profile"
                className="hover-scale"
                asChild
              >
                <Link href="/profile">
                  <User className="h-4 w-4" />
                </Link>
              </Button>

              <Button 
                variant="outline" 
                size="sm" 
                className="hidden md:inline-flex"
                onClick={logout}
              >
                <LogOut className="mr-2 h-4 w-4" />
                Logout
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/login">Sign In</Link>
              </Button>
              <Button size="sm" asChild>
                <Link href="/register">Sign Up</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
