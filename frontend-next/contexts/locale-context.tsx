"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import axios from "axios";

type Locale = "en" | "es" | "fr" | "de" | "it";

interface LocaleContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  messages: Record<string, any>;
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const [messages, setMessages] = useState<Record<string, any>>({});

  // Load messages when locale changes
  useEffect(() => {
    async function loadMessages() {
      try {
        const response = await fetch(`/messages/${locale}.json`);
        const data = await response.json();
        setMessages(data);
      } catch (error) {
        console.error(`Failed to load messages for locale: ${locale}`, error);
        // Fallback to English
        if (locale !== "en") {
          const response = await fetch(`/messages/en.json`);
          const data = await response.json();
          setMessages(data);
        }
      }
    }
    loadMessages();
  }, [locale]);

  // Fetch user's language preference from backend
  useEffect(() => {
    async function fetchLanguage() {
      try {
        const token = localStorage.getItem("access_token");
        if (token) {
          const response = await axios.get(
            `${process.env.NEXT_PUBLIC_API_URL}/api/v1/settings`,
            {
              headers: { Authorization: `Bearer ${token}` },
            }
          );
          if (response.data.language) {
            setLocaleState(response.data.language as Locale);
          }
        }
      } catch (error) {
        console.error("Failed to fetch language preference:", error);
      }
    }
    fetchLanguage();
  }, []);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
  };

  return (
    <LocaleContext.Provider value={{ locale, setLocale, messages }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("useLocale must be used within a LocaleProvider");
  }
  return context;
}

// Helper hook for translations
export function useTranslations(namespace?: string) {
  const { messages } = useLocale();

  return function t(key: string): string {
    const fullKey = namespace ? `${namespace}.${key}` : key;
    const keys = fullKey.split(".");
    let value: any = messages;

    for (const k of keys) {
      if (value && typeof value === "object" && k in value) {
        value = value[k];
      } else {
        return fullKey; // Return key if translation not found
      }
    }

    return typeof value === "string" ? value : fullKey;
  };
}
