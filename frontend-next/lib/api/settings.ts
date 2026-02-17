import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UserSettings {
  id: string;
  theme: string;
  language: string;
  notifications_enabled: boolean;
  email_notifications: boolean;
  compact_mode: boolean;
}

export interface UserSettingsUpdate {
  theme?: string;
  language?: string;
  notifications_enabled?: boolean;
  email_notifications?: boolean;
  compact_mode?: boolean;
}

export const settingsApi = {
  get: async (): Promise<UserSettings> => {
    const token = localStorage.getItem("access_token");
    const response = await axios.get(`${API_URL}/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  update: async (updates: UserSettingsUpdate): Promise<UserSettings> => {
    const token = localStorage.getItem("access_token");
    const response = await axios.patch(`${API_URL}/settings`, updates, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },
};
