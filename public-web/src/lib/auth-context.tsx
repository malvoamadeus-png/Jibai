"use client";

import type { SupabaseClient, User } from "@supabase/supabase-js";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { getPublicApiBaseUrl } from "@/lib/env";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { UserProfile } from "@/lib/types";

type AuthContextValue = {
  supabase: SupabaseClient;
  profile: UserProfile | null;
  loading: boolean;
  authAvailable: boolean;
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

function profileFromUser(user: User): UserProfile | null {
  if (!user.email) {
    return null;
  }

  return {
    id: user.id,
    email: user.email,
    displayName: metadataString(user, "full_name") || user.email.split("@")[0],
    avatarUrl: metadataString(user, "avatar_url"),
    isAdmin: false,
  };
}

async function fetchProfile(accessToken: string): Promise<UserProfile> {
  const response = await fetch(`${getPublicApiBaseUrl()}/api/public/me`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    let detail = "Profile sync failed";
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string" && payload.detail) detail = payload.detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  const row = await response.json();
  return {
    id: String(row.id),
    email: String(row.email),
    displayName: String(row.displayName || row.display_name || row.email),
    avatarUrl: String(row.avatarUrl || row.avatar_url || ""),
    isAdmin: Boolean(row.isAdmin ?? row.is_admin),
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const supabase = useMemo(() => getSupabaseBrowserClient(), []);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [authAvailable, setAuthAvailable] = useState(true);
  const currentUserIdRef = useRef<string | null>(null);

  const loadProfile = useCallback(
    async ({ showLoading = false }: { showLoading?: boolean } = {}) => {
      if (showLoading) setLoading(true);

      try {
        const [{ data: userData }, { data: sessionData }] = await Promise.all([
          supabase.auth.getUser(),
          supabase.auth.getSession(),
        ]);
        setAuthAvailable(true);
        const user = userData.user;
        if (!user?.email) {
          currentUserIdRef.current = null;
          setProfile(null);
          return;
        }

        currentUserIdRef.current = user.id;
        const accessToken = sessionData.session?.access_token;
        if (!accessToken) {
          setProfile(profileFromUser(user));
          return;
        }
        try {
          setProfile(await fetchProfile(accessToken));
        } catch (error) {
          console.error(error);
          setProfile(profileFromUser(user));
        }
      } catch (error) {
        console.error(error);
        currentUserIdRef.current = null;
        setProfile(null);
        setAuthAvailable(false);
      } finally {
        setLoading(false);
      }
    },
    [supabase],
  );

  const refreshProfile = useCallback(async () => {
    await loadProfile();
  }, [loadProfile]);

  const refreshProfileSoon = useCallback(() => {
    setTimeout(() => {
      loadProfile().catch(console.error);
    }, 0);
  }, [loadProfile]);

  const handleSignOut = useCallback(() => {
    currentUserIdRef.current = null;
    setProfile(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    Promise.resolve().then(() => loadProfile({ showLoading: true })).catch(console.error);
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "INITIAL_SESSION" || event === "TOKEN_REFRESHED") {
        return;
      }

      if (event === "SIGNED_OUT") {
        handleSignOut();
        return;
      }

      if (event === "SIGNED_IN") {
        const nextUserId = session?.user?.id ?? null;
        if (nextUserId && nextUserId === currentUserIdRef.current) {
          return;
        }
      }

      refreshProfileSoon();
    });
    return () => subscription.unsubscribe();
  }, [handleSignOut, loadProfile, refreshProfileSoon, supabase]);

  const signIn = useCallback(async () => {
    if (!authAvailable) {
      throw new Error("Supabase Auth is temporarily unavailable.");
    }
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  }, [authAvailable, supabase]);

  const signOut = useCallback(async () => {
    if (!authAvailable) {
      setProfile(null);
      window.location.assign("/");
      return;
    }
    await supabase.auth.signOut();
    setProfile(null);
    window.location.assign("/");
  }, [authAvailable, supabase]);

  const value = useMemo(
    () => ({ loading, profile, refreshProfile, signIn, signOut, supabase, authAvailable }),
    [authAvailable, loading, profile, refreshProfile, signIn, signOut, supabase],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
