"use client"

import { useEffect, useState } from "react"
import { useRouter, usePathname } from "next/navigation"
import { Loader2 } from "lucide-react"
import { isAuthenticated } from "@/lib/auth"

const PUBLIC_ROUTES = ['/', '/login', '/register']

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const checkAuth = () => {
      const authed = isAuthenticated()
      const isPublicRoute = PUBLIC_ROUTES.includes(pathname)

      if (!authed && !isPublicRoute) {
        router.push('/login')
      } else if (authed && (pathname === '/login' || pathname === '/register')) {
        router.push('/dashboard')
      }
      
      setIsLoading(false)
    }

    checkAuth()
  }, [pathname, router])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loader2 className="h-12 w-12 animate-spin text-indigo-600" />
      </div>
    )
  }

  return <>{children}</>
}
