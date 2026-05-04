"use client";

import type { SupabaseClient, User } from "@supabase/supabase-js";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { UserProfile } from "@/lib/types";

type AuthContextValue = {
  supabase: SupabaseClient;
  profile: UserProfile | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function metadataString(user: User, key: string) {
  const value = user.user_metadata?.[key];
  return typeof value === "string" ? value : "";
}

function mapProfile(row: any): UserProfile {
  return {
    id: String(row.id),
    email: String(row.email),
    displayName: String(row.display_name || row.email),
    avatarUrl: String(row.avatar_url || ""),
    isAdmin: Boolean(row.is_admin),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const supabase = useMemo(() => getSupabaseBrowserClient(), []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    setLoading(true);
    const { data: userData } = await supabase.auth.getUser();
    const user = userData.user;
    if (!user?.email) {
      setProfile(null);
      setLoading(false);
      return;
    }

    const displayName = metadataString(user, "full_name") || user.email.split("@")[0];
    const avatarUrl = metadataString(user, "avatar_url");
    const { data, error } = await supabase.rpc("upsert_current_profile", {
      avatar_url_arg: avatarUrl,
      display_name_arg: displayName,
    });

    if (error) {
      console.error(error);
      setProfile(null);
      setLoading(false);
      return;
    }

    setProfile(mapProfile(data));
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    Promise.resolve().then(refreshProfile).catch(console.error);
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(() => {
      setTimeout(() => {
        refreshProfile().catch(console.error);
      }, 0);
    });
    return () => subscription.unsubscribe();
  }, [refreshProfile, supabase]);

  const signIn = useCallback(async () => {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  }, [supabase]);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setProfile(null);
    window.location.assign("/");
  }, [supabase]);

  const value = useMemo(
    () => ({ loading, profile, refreshProfile, signIn, signOut, supabase }),
    [loading, profile, refreshProfile, signIn, signOut, supabase],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
