"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  User,
  Mail,
  Building2,
  MapPin,
  Globe,
  Camera,
  Save,
  X,
  Edit,
  Shield,
} from "lucide-react";
import axios from "axios";

interface UserProfile {
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

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    full_name: "",
    bio: "",
    avatar_url: "",
    company: "",
    location: "",
    website: "",
  });

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    try {
      const token = localStorage.getItem("access_token");
      const response = await axios.get(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/profile`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      setProfile(response.data);
      setFormData({
        full_name: response.data.full_name || "",
        bio: response.data.bio || "",
        avatar_url: response.data.avatar_url || "",
        company: response.data.company || "",
        location: response.data.location || "",
        website: response.data.website || "",
      });
    } catch (error) {
      console.error("Failed to fetch profile:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    try {
      const token = localStorage.getItem("access_token");
      const response = await axios.patch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/profile`,
        formData,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      setProfile(response.data);
      setEditing(false);
    } catch (error) {
      console.error("Failed to update profile:", error);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (profile) {
      setFormData({
        full_name: profile.full_name || "",
        bio: profile.bio || "",
        avatar_url: profile.avatar_url || "",
        company: profile.company || "",
        location: profile.location || "",
        website: profile.website || "",
      });
    }
    setEditing(false);
  };

  const getInitials = () => {
    if (profile?.full_name) {
      return profile.full_name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);
    }
    return profile?.email.charAt(0).toUpperCase() || "U";
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
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <User className="h-8 w-8 text-primary" />
                <h1 className="text-3xl font-bold text-foreground">Profile</h1>
              </div>
              <p className="text-muted-foreground">
                Manage your personal information and public profile
              </p>
            </div>
            {!editing && (
              <Button
                onClick={() => setEditing(true)}
                className="gap-2 hover-lift"
              >
                <Edit className="h-4 w-4" />
                Edit Profile
              </Button>
            )}
          </div>
        </div>

        <div className="space-y-6">
          {/* Avatar & Basic Info */}
          <Card className="p-8 glass hover-lift animate-fade-in-up">
            <div className="flex flex-col md:flex-row gap-8 items-start">
              {/* Avatar */}
              <div className="flex flex-col items-center gap-4">
                <div className="relative group">
                  {profile?.avatar_url ? (
                    <img
                      src={profile.avatar_url}
                      alt="Profile"
                      className="h-32 w-32 rounded-full object-cover border-4 border-primary/20 shadow-lg"
                    />
                  ) : (
                    <div className="h-32 w-32 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center border-4 border-primary/20 shadow-lg">
                      <span className="text-4xl font-bold text-white">
                        {getInitials()}
                      </span>
                    </div>
                  )}
                  {editing && (
                    <button className="absolute inset-0 bg-black/50 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                      <Camera className="h-8 w-8 text-white" />
                    </button>
                  )}
                </div>
                <div className="text-center">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Shield className="h-4 w-4" />
                    <span>Verified Account</span>
                  </div>
                </div>
              </div>

              {/* Basic Info */}
              <div className="flex-1 space-y-6">
                {editing ? (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">
                        Full Name
                      </label>
                      <input
                        type="text"
                        value={formData.full_name}
                        onChange={(e) =>
                          setFormData({ ...formData, full_name: e.target.value })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all"
                        placeholder="Enter your full name"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">
                        Bio
                      </label>
                      <textarea
                        value={formData.bio}
                        onChange={(e) =>
                          setFormData({ ...formData, bio: e.target.value })
                        }
                        rows={3}
                        className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all resize-none"
                        placeholder="Tell us about yourself"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">
                        Avatar URL
                      </label>
                      <input
                        type="url"
                        value={formData.avatar_url}
                        onChange={(e) =>
                          setFormData({ ...formData, avatar_url: e.target.value })
                        }
                        className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all"
                        placeholder="https://example.com/avatar.jpg"
                      />
                    </div>

                    <div className="flex gap-3 pt-4">
                      <Button
                        type="submit"
                        disabled={saving}
                        className="gap-2 hover-lift flex-1"
                      >
                        <Save className="h-4 w-4" />
                        {saving ? "Saving..." : "Save Changes"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={handleCancel}
                        disabled={saving}
                        className="gap-2 hover-lift"
                      >
                        <X className="h-4 w-4" />
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <h2 className="text-2xl font-bold text-foreground">
                        {profile?.full_name || "No name set"}
                      </h2>
                      <p className="text-muted-foreground flex items-center gap-2 mt-1">
                        <Mail className="h-4 w-4" />
                        {profile?.email}
                      </p>
                    </div>

                    {profile?.bio && (
                      <div>
                        <p className="text-foreground leading-relaxed">
                          {profile.bio}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Additional Information */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.1s" }}>
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Additional Information
            </h3>

            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    Company
                  </label>
                  <input
                    type="text"
                    value={formData.company}
                    onChange={(e) =>
                      setFormData({ ...formData, company: e.target.value })
                    }
                    className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all"
                    placeholder="Your company name"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                    <MapPin className="h-4 w-4" />
                    Location
                  </label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) =>
                      setFormData({ ...formData, location: e.target.value })
                    }
                    className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all"
                    placeholder="City, Country"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2 flex items-center gap-2">
                    <Globe className="h-4 w-4" />
                    Website
                  </label>
                  <input
                    type="url"
                    value={formData.website}
                    onChange={(e) =>
                      setFormData({ ...formData, website: e.target.value })
                    }
                    className="w-full px-4 py-2 rounded-lg border border-border bg-background text-foreground focus:ring-2 focus:ring-primary focus:outline-none transition-all"
                    placeholder="https://yourwebsite.com"
                  />
                </div>
              </div>
            ) : (
              <div className="grid md:grid-cols-3 gap-4">
                {profile?.company && (
                  <div className="p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-2 text-muted-foreground mb-1">
                      <Building2 className="h-4 w-4" />
                      <span className="text-xs font-medium">Company</span>
                    </div>
                    <p className="text-foreground font-medium">{profile.company}</p>
                  </div>
                )}

                {profile?.location && (
                  <div className="p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-2 text-muted-foreground mb-1">
                      <MapPin className="h-4 w-4" />
                      <span className="text-xs font-medium">Location</span>
                    </div>
                    <p className="text-foreground font-medium">{profile.location}</p>
                  </div>
                )}

                {profile?.website && (
                  <div className="p-4 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors">
                    <div className="flex items-center gap-2 text-muted-foreground mb-1">
                      <Globe className="h-4 w-4" />
                      <span className="text-xs font-medium">Website</span>
                    </div>
                    <a
                      href={profile.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary font-medium hover:underline truncate block"
                    >
                      {profile.website.replace(/^https?:\/\//, "")}
                    </a>
                  </div>
                )}

                {!profile?.company && !profile?.location && !profile?.website && (
                  <div className="col-span-3 text-center py-8">
                    <p className="text-muted-foreground">
                      No additional information added yet
                    </p>
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Account Info */}
          <Card className="p-6 glass hover-lift animate-fade-in-up" style={{ animationDelay: "0.2s" }}>
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Account Information
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-muted/30">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Member Since
                </p>
                <p className="text-foreground font-medium">
                  {new Date(profile?.created_at || "").toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </p>
              </div>
              <div className="p-4 rounded-lg bg-muted/30">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Last Updated
                </p>
                <p className="text-foreground font-medium">
                  {new Date(profile?.updated_at || "").toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
