"use client";

import { useEffect, useState } from "react";
import { useTheme } from "@/contexts/theme-context";
import { useLocale, useTranslations } from "@/contexts/locale-context";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Settings as SettingsIcon,
  Palette,
  Globe,
  Bell,
  Mail,
  Monitor,
  Moon,
  Sun,
  Waves,
  TreePine,
  Sunset as SunsetIcon,
  Sparkles,
  Check,
} from "lucide-react";
import axios from "axios";

interface UserSettings {
  id: string;
  theme: string;
  language: string;
  notifications_enabled: boolean;
  email_notifications: boolean;
  compact_mode: boolean;
}

const themes = [
  { id: "light", name: "Light", icon: Sun, color: "bg-gradient-to-br from-blue-50 to-indigo-100" },
  { id: "dark", name: "Dark", icon: Moon, color: "bg-gradient-to-br from-slate-800 to-slate-900" },
  { id: "ocean", name: "Ocean", icon: Waves, color: "bg-gradient-to-br from-blue-400 to-cyan-500" },
  { id: "forest", name: "Forest", icon: TreePine, color: "bg-gradient-to-br from-green-500 to-emerald-600" },
  { id: "sunset", name: "Sunset", icon: SunsetIcon, color: "bg-gradient-to-br from-orange-400 to-pink-500" },
  { id: "purple", name: "Purple Dream", icon: Sparkles, color: "bg-gradient-to-br from-purple-500 to-pink-500" },
];

const languages = [
  { id: "en", name: "English", flag: "🇺🇸" },
  { id: "es", name: "Español", flag: "🇪🇸" },
  { id: "fr", name: "Français", flag: "🇫🇷" },
  { id: "de", name: "Deutsch", flag: "🇩🇪" },
  { id: "it", name: "Italiano", flag: "🇮🇹" },
];

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { locale, setLocale } = useLocale();
  const t = useTranslations("settings");
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const token = localStorage.getItem("access_token");
      const response = await axios.get(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/settings`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      setSettings(response.data);
      // Sync theme from backend
      if (response.data.theme && response.data.theme !== theme) {
        setTheme(response.data.theme as "light" | "dark" | "ocean" | "forest" | "sunset" | "purple");
      }
    } catch (error) {
      console.error("Failed to fetch settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const updateSettings = async (updates: Partial<UserSettings>) => {
    setSaving(true);
    try {
      const token = localStorage.getItem("access_token");
      const response = await axios.patch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/settings`,
        updates,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      setSettings(response.data);
    } catch (error) {
      console.error("Failed to update settings:", error);
    } finally {
      setSaving(false);
    }
  };

  const handleThemeChange = (newTheme: string) => {
    setTheme(newTheme as "light" | "dark" | "ocean" | "forest" | "sunset" | "purple");
    updateSettings({ theme: newTheme });
  };

  const handleLanguageChange = (language: string) => {
    setLocale(language as "en" | "es" | "fr" | "de" | "it");
    updateSettings({ language });
  };

  const toggleNotifications = () => {
    if (settings) {
      updateSettings({ notifications_enabled: !settings.notifications_enabled });
    }
  };

  const toggleEmailNotifications = () => {
    if (settings) {
      updateSettings({ email_notifications: !settings.email_notifications });
    }
  };

  const toggleCompactMode = () => {
    if (settings) {
      updateSettings({ compact_mode: !settings.compact_mode });
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background py-8 px-4 animate-fade-in-up">
      <div className="container mx-auto max-w-4xl">
        {/* Header */}
        <div className="mb-8 animate-fade-in-down">
          <div className="flex items-center gap-3 mb-2">
            <SettingsIcon className="h-8 w-8 text-primary" />
            <h1 className="text-3xl font-bold text-foreground">{t("title")}</h1>
          </div>
          <p className="text-muted-foreground">
            {t("description")}
          </p>
        </div>

        <div className="space-y-6">
          {/* Theme Selection */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-full bg-primary/10 p-2">
                <Palette className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">{t("theme.title")}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("theme.description")}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {themes.map((themeOption) => {
                const Icon = themeOption.icon;
                const isActive = theme === themeOption.id;

                return (
                  <button
                    key={themeOption.id}
                    onClick={() => handleThemeChange(themeOption.id)}
                    className={`relative p-4 rounded-xl border-2 transition-all duration-200 hover-lift ${
                      isActive
                        ? "border-primary shadow-lg"
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <div className={`h-20 rounded-lg mb-3 ${themeOption.color} flex items-center justify-center`}>
                      <Icon className="h-8 w-8 text-white drop-shadow-lg" />
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-foreground">
                        {t(`theme.${themeOption.id}`)}
                      </span>
                      {isActive && (
                        <Check className="h-5 w-5 text-primary animate-scale-in" />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>

          {/* Language */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-full bg-primary/10 p-2">
                <Globe className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">{t("language.title")}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("language.description")}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {languages.map((lang) => {
                const isActive = settings?.language === lang.id;

                return (
                  <button
                    key={lang.id}
                    onClick={() => handleLanguageChange(lang.id)}
                    className={`p-3 rounded-lg border-2 transition-all duration-200 hover-lift ${
                      isActive
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-2xl">{lang.flag}</span>
                      <span className="text-sm font-medium text-foreground">
                        {lang.name}
                      </span>
                      {isActive && (
                        <Check className="h-4 w-4 text-primary ml-auto animate-scale-in" />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>

          {/* Notifications */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-full bg-primary/10 p-2">
                <Bell className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">{t("notifications.title")}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("notifications.description")}
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-3">
                  <Bell className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">{t("notifications.push.title")}</p>
                    <p className="text-sm text-muted-foreground">
                      {t("notifications.push.description")}
                    </p>
                  </div>
                </div>
                <button
                  onClick={toggleNotifications}
                  className={`relative h-6 w-11 rounded-full transition-colors duration-200 ${
                    settings?.notifications_enabled
                      ? "bg-primary"
                      : "bg-muted-foreground/30"
                  }`}
                >
                  <div
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                      settings?.notifications_enabled
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                <div className="flex items-center gap-3">
                  <Mail className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">{t("notifications.email.title")}</p>
                    <p className="text-sm text-muted-foreground">
                      {t("notifications.email.description")}
                    </p>
                  </div>
                </div>
                <button
                  onClick={toggleEmailNotifications}
                  className={`relative h-6 w-11 rounded-full transition-colors duration-200 ${
                    settings?.email_notifications
                      ? "bg-primary"
                      : "bg-muted-foreground/30"
                  }`}
                >
                  <div
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                      settings?.email_notifications
                        ? "translate-x-5"
                        : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
            </div>
          </Card>

          {/* Display */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-full bg-primary/10 p-2">
                <Monitor className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">{t("display.title")}</h2>
                <p className="text-sm text-muted-foreground">
                  {t("display.description")}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
              <div className="flex items-center gap-3">
                <Monitor className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium text-foreground">{t("display.compactMode.title")}</p>
                  <p className="text-sm text-muted-foreground">
                    {t("display.compactMode.description")}
                  </p>
                </div>
              </div>
              <button
                onClick={toggleCompactMode}
                className={`relative h-6 w-11 rounded-full transition-colors duration-200 ${
                  settings?.compact_mode ? "bg-primary" : "bg-muted-foreground/30"
                }`}
              >
                <div
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                    settings?.compact_mode ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
          </Card>

          {/* Save indicator */}
          {saving && (
            <div className="fixed bottom-8 right-8 bg-primary text-primary-foreground px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 animate-slide-in-right">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
              <span>{t("saving")}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
