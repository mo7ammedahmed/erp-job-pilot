import { useEffect, useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { I18nProvider } from "@/lib/i18n";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { api, errMsg } from "@/lib/api";
import { FullLoader } from "@/components/common";
import AppShell from "@/components/AppShell";
import Landing from "@/pages/Landing";
import { Login, Register, Forgot, ResetPassword } from "@/pages/AuthPages";
import Onboarding from "@/pages/Onboarding";
import Legal from "@/pages/Legal";
import Dashboard from "@/pages/Dashboard";
import Jobs from "@/pages/Jobs";
import JobDetail from "@/pages/JobDetail";
import CVVault from "@/pages/CVVault";
import Tailor from "@/pages/Tailor";
import Tracker from "@/pages/Tracker";
import Reminders from "@/pages/Reminders";
import SettingsPage from "@/pages/Settings";
import Billing from "@/pages/Billing";
import Admin from "@/pages/Admin";
import Coach from "@/pages/Coach";

function AuthCallback() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const sid = new URLSearchParams(loc.hash.slice(1)).get("session_id");
    api.post("/auth/google/session", { session_id: sid })
      .then(({ data }) => {
        setUser(data);
        window.history.replaceState(null, "", "/app");
        nav(data.onboarded ? "/app" : "/onboarding", { replace: true });
      })
      .catch((e) => { toast.error(errMsg(e)); nav("/login", { replace: true }); });
  }, [loc.hash, nav, setUser]);
  return <FullLoader />;
}

function Protected({ children, allowNotOnboarded }) {
  const { user } = useAuth();
  if (user === null) return <FullLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.onboarded && !allowNotOnboarded) return <Navigate to="/onboarding" replace />;
  return children;
}

function AdminOnly({ children }) {
  const { user } = useAuth();
  return user?.role === "admin" ? children : <Navigate to="/app" replace />;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/legal/:doc" element={<Legal />} />
      <Route path="/onboarding" element={<Protected allowNotOnboarded><Onboarding /></Protected>} />
      <Route path="/app" element={<Protected><AppShell /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="cv" element={<CVVault />} />
        <Route path="tailor/:id" element={<Tailor />} />
        <Route path="tracker" element={<Tracker />} />
        <Route path="reminders" element={<Reminders />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="billing" element={<Billing />} />
        <Route path="coach" element={<Coach />} />
        <Route path="admin" element={<AdminOnly><Admin /></AdminOnly>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster position="top-center" richColors />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  );
}
