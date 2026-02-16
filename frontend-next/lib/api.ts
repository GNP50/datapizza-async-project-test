import axios from "axios"
import { parsePaginationHeaders, PaginatedResult } from "./usePagination"
import { getRefreshToken, setTokens, logout } from "./auth"
// import { encode, decode } from "@msgpack/msgpack"

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json",
  },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  // MessagePack encoding disabled - using standard JSON
  // const contentType = config.headers["Content-Type"]
  // if (contentType === "application/json" && config.data) {
  //   config.headers["Content-Type"] = "application/msgpack"
  //   config.data = encode(config.data)
  //   config.responseType = "arraybuffer"
  // }
  // if (config.method === "get" && !config.responseType) {
  //   config.responseType = "arraybuffer"
  // }

  return config
})

let isRefreshing = false
let failedQueue: Array<{
  resolve: (value?: unknown) => void
  reject: (reason?: unknown) => void
}> = []

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

api.interceptors.response.use(
  (response) => {
    // MessagePack decoding disabled - using standard JSON
    // const contentType = response.headers["content-type"]
    // if (contentType?.includes("application/msgpack") && response.data instanceof ArrayBuffer) {
    //   response.data = decode(new Uint8Array(response.data))
    // }
    return response
  },
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then(() => {
            return api(originalRequest)
          })
          .catch((err) => {
            return Promise.reject(err)
          })
      }

      originalRequest._retry = true
      isRefreshing = true

      const refreshToken = getRefreshToken()

      if (!refreshToken) {
        logout()
        return Promise.reject(error)
      }

      try {
        const response = await axios.post(
          `${api.defaults.baseURL}/api/v1/auth/refresh`,
          { refresh_token: refreshToken }
        )

        const { access_token, refresh_token: new_refresh_token } = response.data
        setTokens(access_token, new_refresh_token)

        originalRequest.headers.Authorization = `Bearer ${access_token}`
        processQueue(null, access_token)

        return api(originalRequest)
      } catch (refreshError) {
        processQueue(new Error("Token refresh failed"), null)
        logout()
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    } else if (!error.response) {
      // Connection error (network down or backend not responding)
      // Dispatch custom event for toast handling
      const connectionErrorEvent = new CustomEvent("connectionError", {
        detail: { message: "Connection error: Unable to reach the server" },
      })
      window.dispatchEvent(connectionErrorEvent)
    }
    return Promise.reject(error)
  }
)

export interface User {
  id: string
  email: string
  name: string
}

export interface Chat {
  id: string
  title: string
  summary?: string
  created_at: string
  updated_at: string
}

export interface SearchResult {
  chat: Chat
  score: number
}

export interface Document {
  id: string
  filename: string
  file_size: number
  mime_type: string
  processed: boolean
  processing_state: string
  web_search_enabled: boolean
  created_at: string
  facts: Fact[]
}

export interface Fact {
  id: string
  content: string
  page_number: number | null
  verification_status: "pending" | "verified" | "debunked" | "uncertain"
  web_source_url: string[]
  confidence_score: number
  verification_reasoning: string | null
  created_at: string
}

export interface DocumentDetail extends Document {
  extracted_content: string | null
  updated_at: string
  facts: Fact[]
}

export interface Flashcard {
  id: string
  front: string
  back: string
  category: string | null
  difficulty: number
  confidence: number
  fact_id: string | null
  created_at: string
}

export interface FactCheck {
  id: string
  claim: string
  verification_status: "pending" | "verified" | "debunked" | "uncertain"
  confidence_score: number
  sources: Record<string, unknown>
  created_at: string
}

export interface Message {
  id: string
  chat_id: string
  role: "user" | "assistant"
  content: string
  created_at: string
  processing_state: string
  fact_checks: FactCheck[]
  documents: Document[]
  response_cached?: boolean
  response_type?: string
  response_metadata?: {
    cached?: boolean
    response_type?: string
    documents_used?: Array<{id: string, filename: string}>
    cache_score?: number
  }
}

export const authApi = {
  login: async (email: string, password: string) => {
    const response = await api.post("/api/v1/auth/login", { email, password })
    return response.data
  },
  register: async (name: string, email: string, password: string) => {
    const response = await api.post("/api/v1/auth/register", { name, email, password })
    return response.data
  },
  me: async () => {
    const response = await api.get<User>("/api/v1/auth/me")
    return response.data
  },
}

export const chatsApi = {
  list: async (page?: number, pageSize?: number): Promise<PaginatedResult<Chat[]>> => {
    const params: Record<string, number> = {}
    if (page !== undefined) params.page = page
    if (pageSize !== undefined) params.page_size = pageSize

    const response = await api.get<Chat[]>("/api/v1/chats", { params })
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
  get: async (id: string) => {
    const response = await api.get<Chat>(`/api/v1/chats/${id}`)
    return response.data
  },
  create: async (title: string) => {
    const response = await api.post<Chat>("/api/v1/chats", { title })
    return response.data
  },
  delete: async (id: string) => {
    await api.delete(`/api/v1/chats/${id}`)
  },
  search: async (query: string, page?: number, pageSize?: number): Promise<PaginatedResult<SearchResult[]>> => {
    const params: Record<string, string | number> = { q: query }
    if (page !== undefined) params.page = page
    if (pageSize !== undefined) params.page_size = pageSize

    const response = await api.get<SearchResult[]>("/api/v1/chats/search", { params })
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
}

export const messagesApi = {
  list: async (chatId: string, page?: number, pageSize?: number): Promise<PaginatedResult<Message[]>> => {
    const params: Record<string, number> = {}
    if (page !== undefined) params.page = page
    if (pageSize !== undefined) params.page_size = pageSize

    const response = await api.get<Message[]>(`/api/v1/chats/${chatId}/messages`, { params })
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
  send: async (chatId: string, content: string) => {
    const response = await api.post<Message>(`/api/v1/chats/${chatId}/messages/json`, { content })
    return response.data
  },
  sendWithFiles: async (chatId: string, content: string, files: File[], webSearchEnabled?: boolean[]) => {
    const formData = new FormData()
    formData.append('content', content)
    files.forEach(file => {
      formData.append('files', file)
    })
    // Send web search settings as JSON array
    if (webSearchEnabled) {
      formData.append('web_search_enabled', JSON.stringify(webSearchEnabled))
    }
    const response = await api.post<Message>(`/api/v1/chats/${chatId}/messages`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'Accept': 'application/json'
      }
    })
    return response.data
  },
  retry: async (chatId: string, messageId: string, skipDocumentProcessing: boolean = true) => {
    const response = await api.post<Message>(
      `/api/v1/chats/${chatId}/messages/${messageId}/retry`,
      { skip_document_processing: skipDocumentProcessing }
    )
    return response.data
  },
  stop: async (chatId: string, messageId: string) => {
    const response = await api.post(`/api/v1/chats/${chatId}/messages/${messageId}/stop`)
    return response.data
  },
  regenerateWithoutCache: async (chatId: string, messageId: string) => {
    const response = await api.post<Message>(`/api/v1/chats/${chatId}/messages/${messageId}/regenerate`)
    return response.data
  },
}

export const documentsApi = {
  get: async (documentId: string) => {
    const response = await api.get<DocumentDetail>(`/api/v1/documents/${documentId}`)
    return response.data
  },
  getFacts: async (
    documentId: string,
    page?: number,
    pageSize?: number,
    verificationStatus?: string[]
  ): Promise<PaginatedResult<Fact[]>> => {
    // Build URLSearchParams to properly handle array parameters
    const searchParams = new URLSearchParams()
    if (page !== undefined) searchParams.append('page', page.toString())
    if (pageSize !== undefined) searchParams.append('page_size', pageSize.toString())
    if (verificationStatus && verificationStatus.length > 0) {
      verificationStatus.forEach(status => {
        searchParams.append('verification_status', status)
      })
    }

    const response = await api.get<Fact[]>(
      `/api/v1/documents/${documentId}/facts?${searchParams.toString()}`
    )
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
  reprocess: async (documentId: string) => {
    const response = await api.post<DocumentDetail>(`/api/v1/documents/${documentId}/reprocess`)
    return response.data
  },
  reprocessFromStage: async (documentId: string, stage: string, enableWebSearch?: boolean) => {
    const response = await api.post<DocumentDetail>(`/api/v1/documents/${documentId}/reprocess-from-stage`, {
      stage,
      enable_web_search: enableWebSearch
    })
    return response.data
  },
  stop: async (documentId: string) => {
    const response = await api.post<DocumentDetail>(`/api/v1/documents/${documentId}/stop`)
    return response.data
  },
  listByChat: async (chatId: string, page?: number, pageSize?: number): Promise<PaginatedResult<DocumentDetail[]>> => {
    const params: Record<string, number> = {}
    if (page !== undefined) params.page = page
    if (pageSize !== undefined) params.page_size = pageSize

    const response = await api.get<DocumentDetail[]>(`/api/v1/chats/${chatId}/documents`, { params })
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
  generateFlashcards: async (documentId: string) => {
    const response = await api.post(`/api/v1/documents/${documentId}/generate-flashcards`)
    return response.data
  },
  getFlashcards: async (documentId: string, page?: number, pageSize?: number): Promise<PaginatedResult<Flashcard[]>> => {
    const params: Record<string, number> = {}
    if (page !== undefined) params.page = page
    if (pageSize !== undefined) params.page_size = pageSize

    const response = await api.get<Flashcard[]>(`/api/v1/documents/${documentId}/flashcards`, { params })
    return {
      data: response.data,
      pagination: parsePaginationHeaders(response),
    }
  },
  download: async (documentId: string) => {
    const response = await api.get<Blob>(`/api/v1/documents/${documentId}/download`, {
      responseType: 'blob',
      headers: {
        'Accept': '*/*'  // Don't request MessagePack for file downloads
      }
    })
    return response
  },
}

// Settings API
export interface UserSettings {
  id: string
  theme: string
  language: string
  notifications_enabled: boolean
  email_notifications: boolean
  compact_mode: boolean
}

export const settingsApi = {
  get: async () => {
    const response = await api.get<UserSettings>("/api/v1/settings")
    return response.data
  },
  update: async (updates: Partial<UserSettings>) => {
    const response = await api.patch<UserSettings>("/api/v1/settings", updates)
    return response.data
  },
}

// Profile API
export interface UserProfile {
  id: string
  user_id: string
  email: string
  full_name: string | null
  bio: string | null
  avatar_url: string | null
  company: string | null
  location: string | null
  website: string | null
  created_at: string
  updated_at: string
}

export const profileApi = {
  get: async () => {
    const response = await api.get<UserProfile>("/api/v1/profile")
    return response.data
  },
  update: async (updates: Partial<UserProfile>) => {
    const response = await api.patch<UserProfile>("/api/v1/profile", updates)
    return response.data
  },
}
