import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUserState] = useState(null);
  const { setLang } = useI18n();
  const setUser = useCallback((u) => {
    setUserState(u);
    if (u && u.lang) setLang(u.lang);
  }, [setLang]);
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch (_) {
      setUserState(false);
      return false;
    }
  }, [setUser]);
  useEffect(() => {
    // Skip /me when returning from Google OAuth; AuthCallback exchanges the session first.
    if (window.location.hash?.includes("session_id=")) return;
    refresh();
  }, [refresh]);
  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    setUserState(false);
  };
  return <AuthCtx.Provider value={{ user, setUser, refresh, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
