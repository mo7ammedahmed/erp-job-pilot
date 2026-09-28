import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Compass } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/lib/i18n";
import { Spinner } from "@/components/common";

const SIDE = "https://images.pexels.com/photos/7984742/pexels-photo-7984742.jpeg?auto=compress&cs=tinysrgb&w=1200";

function Shell({ title, subtitle, children }) {
  const { lang, setLang } = useI18n();
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-6 py-6 sm:px-12">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900 text-white"><Compass className="h-4 w-4" /></div><span className="font-heading text-lg font-bold">JobPilot</span></Link>
          <button data-testid="auth-language-toggle" onClick={() => setLang(lang === "ar" ? "en" : "ar")} className="rounded-lg px-3 py-2 text-sm hover:bg-slate-100">{lang === "ar" ? "English" : "العربية"}</button>
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10 jp-rise">
          <h1 className="font-heading text-3xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-2 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </div>
      <div className="relative hidden lg:block"><img src={SIDE} alt="" className="absolute inset-0 h-full w-full object-cover" /><div className="absolute inset-0 bg-emerald-950/40" /></div>
    </div>
  );
}

function GoogleButton() {
  const { t } = useI18n();
  const go = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/app";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };
  return (
    <Button type="button" variant="outline" className="w-full" onClick={go} data-testid="google-login-button">
      <svg className="me-2 h-4 w-4" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" /><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" /><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" /><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" /></svg>
      {t("Continue with Google")}
    </Button>
  );
}

const Divider = () => {
  const { t } = useI18n();
  return <div className="my-5 flex items-center gap-3 text-xs text-slate-400"><div className="h-px flex-1 bg-slate-200" />{t("or")}<div className="h-px flex-1 bg-slate-200" /></div>;
};

export function Login() {
  const { t } = useI18n();
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/login", f);
      setUser(data);
      nav(data.onboarded ? "/app" : "/onboarding");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title={t("Welcome back")} subtitle={t("Log in to continue your job search.")}>
      <GoogleButton /><Divider />
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5"><Label>{t("Email")}</Label><Input data-testid="login-email-input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="space-y-1.5"><div className="flex justify-between"><Label>{t("Password")}</Label><Link to="/forgot" className="text-xs text-emerald-800 hover:underline" data-testid="forgot-link">{t("Forgot password?")}</Link></div>
          <Input data-testid="login-password-input" type="password" required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
        <Button data-testid="login-submit-button" disabled={busy} className="w-full bg-emerald-900 hover:bg-emerald-800">{busy && <Spinner className="me-2" />}{t("Log in")}</Button>
      </form>
      <p className="mt-6 text-sm text-slate-500">{t("New to JobPilot?")} <Link to="/register" className="font-medium text-emerald-800 hover:underline" data-testid="register-link">{t("Create an account")}</Link></p>
    </Shell>
  );
}

export function Register() {
  const { t, lang } = useI18n();
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/register", { ...f, lang });
      setUser(data);
      nav("/onboarding");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Shell title={t("Create your account")} subtitle={t("Free plan — no card needed.")}>
      <GoogleButton /><Divider />
      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-1.5"><Label>{t("Full name")}</Label><Input data-testid="register-name-input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>{t("Email")}</Label><Input data-testid="register-email-input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="space-y-1.5"><Label>{t("Password")}</Label><Input data-testid="register-password-input" type="password" minLength={8} required value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <p className="text-xs text-slate-400">{t("At least 8 characters")}</p></div>
        <Button data-testid="register-submit-button" disabled={busy} className="w-full bg-emerald-900 hover:bg-emerald-800">{busy && <Spinner className="me-2" />}{t("Create account")}</Button>
      </form>
      <p className="mt-6 text-sm text-slate-500">{t("Already have an account?")} <Link to="/login" className="font-medium text-emerald-800 hover:underline">{t("Log in")}</Link></p>
    </Shell>
  );
}

export function Forgot() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    await api.post("/auth/forgot-password", { email }).catch(() => {});
    setSent(true);
  };
  return (
    <Shell title={t("Reset password")} subtitle={t("We'll email you a reset link.")}>
      {sent ? <p data-testid="forgot-sent" className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900">{t("If an account exists for that email, a reset link is on its way.")}</p> :
        <form onSubmit={submit} className="space-y-4">
          <Input data-testid="forgot-email-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          <Button data-testid="forgot-submit-button" className="w-full bg-emerald-900 hover:bg-emerald-800">{t("Send reset link")}</Button>
        </form>}
      <Link to="/login" className="mt-6 inline-block text-sm text-emerald-800 hover:underline">{t("Back to login")}</Link>
    </Shell>
  );
}

export function ResetPassword() {
  const { t } = useI18n();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/auth/reset-password", { token: sp.get("token"), password });
      toast.success(t("Password updated. Please log in."));
      nav("/login");
    } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <Shell title={t("Choose a new password")}>
      <form onSubmit={submit} className="space-y-4">
        <Input data-testid="reset-password-input" type="password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button data-testid="reset-submit-button" className="w-full bg-emerald-900 hover:bg-emerald-800">{t("Update password")}</Button>
      </form>
    </Shell>
  );
}
