import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface UserProfile {
  id: string;
  user_id: string;
  email: string;
  full_name: string | null;
  bio: string | null;
  avatar_url: string | null;
  company: string | null;
  location: string | null;
  website: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserProfileUpdate {
  full_name?: string;
  bio?: string;
  avatar_url?: string;
  company?: string;
  location?: string;
  website?: string;
}

export const profileApi = {
  get: async (): Promise<UserProfile> => {
    const token = localStorage.getItem("access_token");
    const response = await axios.get(`${API_URL}/profile`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  update: async (updates: UserProfileUpdate): Promise<UserProfile> => {
    const token = localStorage.getItem("access_token");
    const response = await axios.patch(`${API_URL}/profile`, updates, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },
};
