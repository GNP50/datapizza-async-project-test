"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowRight, MessageSquare, FileText, CheckCircle, Sparkles, Zap, Shield } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { isAuthenticated } from "@/lib/auth"

export default function HomePage() {
  const [isAuthed, setIsAuthed] = useState(false)

  useEffect(() => {
    setIsAuthed(isAuthenticated())
  }, [])

  return (
    <div className="container mx-auto px-4 py-12">
      <section className="mb-16 text-center">
        <Badge variant="secondary" className="mb-4">
          <Sparkles className="mr-1 h-3 w-3" />
          Powered by AI
        </Badge>
        <h1 className="mb-4 text-5xl font-bold tracking-tight text-slate-900">
          AI-Powered Conversations
          <br />
          <span className="text-indigo-600">Simplified</span>
        </h1>
        <p className="mx-auto mb-8 max-w-2xl text-lg text-slate-500">
          Experience intelligent chat with document processing, fact-checking, and advanced AI capabilities. Built for modern teams.
        </p>
        <div className="flex items-center justify-center gap-4">
          {isAuthed ? (
            <Button size="lg" asChild>
              <Link href="/dashboard">
                Go to Dashboard
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          ) : (
            <>
              <Button size="lg" asChild>
                <Link href="/register">
                  Get Started
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/login">Sign In</Link>
              </Button>
            </>
          )}
        </div>
      </section>

      <section className="mb-16">
        <div className="mb-8 text-center">
          <h2 className="mb-2 text-3xl font-bold text-slate-900">Features</h2>
          <p className="text-slate-500">Everything you need for intelligent conversations</p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 transition-colors group-hover:bg-indigo-600 group-hover:text-white">
                <MessageSquare className="h-6 w-6" />
              </div>
              <CardTitle>Smart Conversations</CardTitle>
              <CardDescription>
                Context-aware AI that understands your needs and provides relevant responses.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-violet-100 text-violet-600 transition-colors group-hover:bg-violet-600 group-hover:text-white">
                <FileText className="h-6 w-6" />
              </div>
              <CardTitle>Document Processing</CardTitle>
              <CardDescription>
                Upload PDFs, images, and documents for intelligent analysis and extraction.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600 transition-colors group-hover:bg-emerald-600 group-hover:text-white">
                <CheckCircle className="h-6 w-6" />
              </div>
              <CardTitle>Fact Checking</CardTitle>
              <CardDescription>
                Automatic verification of information with source attribution and confidence scores.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-100 text-amber-600 transition-colors group-hover:bg-amber-600 group-hover:text-white">
                <Zap className="h-6 w-6" />
              </div>
              <CardTitle>Lightning Fast</CardTitle>
              <CardDescription>
                Optimized performance with real-time responses and instant document processing.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-rose-100 text-rose-600 transition-colors group-hover:bg-rose-600 group-hover:text-white">
                <Shield className="h-6 w-6" />
              </div>
              <CardTitle>Secure & Private</CardTitle>
              <CardDescription>
                Enterprise-grade security with end-to-end encryption and data privacy.
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="group">
            <CardHeader>
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-100 text-cyan-600 transition-colors group-hover:bg-cyan-600 group-hover:text-white">
                <Sparkles className="h-6 w-6" />
              </div>
              <CardTitle>AI-Powered</CardTitle>
              <CardDescription>
                Leveraging cutting-edge language models for natural, intelligent interactions.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
      </section>

      <section className="mb-16">
        <Card className="bg-gradient-to-br from-indigo-50 to-violet-50 border-indigo-200">
          <CardHeader className="text-center">
            <CardTitle className="text-3xl">Ready to get started?</CardTitle>
            <CardDescription className="text-base">
              {isAuthed 
                ? "Continue your AI-powered conversations"
                : "Join thousands of teams using AiFactChecker to enhance productivity"
              }
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            {isAuthed ? (
              <Button size="lg" asChild>
                <Link href="/dashboard">
                  Go to Dashboard
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            ) : (
              <Button size="lg" asChild>
                <Link href="/register">
                  Create Account
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
