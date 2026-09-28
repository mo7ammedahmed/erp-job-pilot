import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Briefcase, FileText, KanbanSquare, Bell, CreditCard, Settings, Shield, LogOut, Menu, Languages, Compass, Users } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";

const NAV = [
  ["/app", "Dashboard", LayoutDashboard, true], ["/app/jobs", "Job feed", Briefcase], ["/app/cv", "CV vault", FileText],
  ["/app/tracker", "Tracker", KanbanSquare], ["/app/reminders", "Reminders", Bell], ["/app/coach", "Coaching", Users], ["/app/billing", "Plan & usage", CreditCard],
  ["/app/settings", "Settings", Settings],
];

function NavLinks({ onNav }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const items = user?.role === "admin" ? [...NAV, ["/app/admin", "Admin", Shield]] : NAV;
  return (
    <nav className="flex flex-col gap-0.5">
      {items.map(([to, label, Icon, end]) => (
        <NavLink key={to} to={to} end={end} onClick={onNav} data-testid={`nav-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
          className={({ isActive }) => `jp-nav ${isActive ? "jp-nav-active" : ""}`}>
          <Icon className="h-4 w-4 shrink-0" /><span>{t(label)}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-2 py-1">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900 text-white"><Compass className="h-4 w-4" /></div>
      <span className="font-heading text-lg font-bold tracking-tight">JobPilot</span>
    </div>
  );
}

function Notifications() {
  const { t, fmtDateTime } = useI18n();
  const nav = useNavigate();
  const [data, setData] = useState({ items: [], unread: 0 });
  const load = () => api.get("/notifications").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => { load(); const i = setInterval(load, 60000); return () => clearInterval(i); }, []);
  const readAll = () => api.post("/notifications/read-all").then(load);
  return (
    <Popover onOpenChange={(o) => o && data.unread && readAll()}>
      <PopoverTrigger asChild>
        <button data-testid="notifications-bell" className="relative rounded-lg p-2 hover:bg-slate-100">
          <Bell className="h-5 w-5 text-slate-700" />
          {data.unread > 0 && <span data-testid="notifications-unread" className="absolute -top-0.5 end-0 rounded-full bg-rose-600 px-1.5 text-[10px] font-bold text-white">{data.unread}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 bg-white p-0">
        <div className="border-b px-4 py-3 text-sm font-semibold">{t("Notifications")}</div>
        <div className="max-h-96 overflow-y-auto">
          {data.items.length === 0 && <div className="p-4 text-sm text-slate-500">{t("Nothing new")}</div>}
          {data.items.map((n) => (
            <button key={n.notification_id} onClick={() => n.link && nav(n.link)} className="block w-full border-b px-4 py-3 text-start hover:bg-slate-50">
              <div className="text-sm text-slate-900">{n.title}</div>
              <div className="mt-0.5 font-mono text-[11px] text-slate-400">{fmtDateTime(n.created_at)}</div>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function UpgradeDialog() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const h = (e) => setInfo(e.detail);
    window.addEventListener("jp:limit", h);
    return () => window.removeEventListener("jp:limit", h);
  }, []);
  return (
    <Dialog open={!!info} onOpenChange={(o) => !o && setInfo(null)}>
      <DialogContent className="bg-white" data-testid="upgrade-dialog">
        <DialogHeader>
          <DialogTitle>{t("You've reached your plan limit")}</DialogTitle>
          <DialogDescription>{t("Your data is safe. Upgrade to keep going this month.")} ({t(info?.kind || "")})</DialogDescription>
        </DialogHeader>
        <Button data-testid="upgrade-dialog-cta" className="bg-emerald-900 hover:bg-emerald-800" onClick={() => { setInfo(null); nav("/app/billing"); }}>{t("See plans")}</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const { t, lang, setLang, rtl } = useI18n();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const switchLang = () => {
    const l = lang === "ar" ? "en" : "ar";
    setLang(l);
    api.patch("/me", { lang: l }).catch(() => {});
  };
  const doLogout = async () => { await logout(); nav("/login"); };
  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <aside className="fixed inset-y-0 start-0 z-30 hidden w-60 flex-col border-e border-slate-200 bg-white p-4 lg:flex">
        <Brand />
        <div className="mt-6 flex-1"><NavLinks /></div>
        <div className="rounded-lg bg-slate-50 p-3 text-xs">
          <div className="truncate font-semibold text-slate-900">{user?.name}</div>
          <div className="truncate text-slate-500">{user?.email}</div>
          <div className="mt-2 inline-block rounded bg-emerald-900 px-2 py-0.5 font-mono text-[10px] uppercase text-white" data-testid="sidebar-plan">{user?.plan_info?.plan_id || user?.plan}</div>
        </div>
      </aside>
      <div className="lg:ps-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-slate-200 bg-white/85 px-4 backdrop-blur-xl sm:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild><button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" data-testid="mobile-menu-button"><Menu className="h-5 w-5" /></button></SheetTrigger>
            <SheetContent side={rtl ? "right" : "left"} className="w-64 bg-white p-4"><Brand /><div className="mt-6"><NavLinks onNav={() => setOpen(false)} /></div></SheetContent>
          </Sheet>
          <div className="lg:hidden"><Brand /></div>
          <div className="ms-auto flex items-center gap-1">
            <button onClick={switchLang} data-testid="language-toggle" className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium hover:bg-slate-100">
              <Languages className="h-4 w-4" />{lang === "ar" ? "EN" : "العربية"}
            </button>
            <Notifications />
            <button onClick={doLogout} data-testid="logout-button" className="rounded-lg p-2 hover:bg-slate-100" title={t("Log out")}><LogOut className="h-5 w-5 text-slate-700 rtl:rotate-180" /></button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8"><Outlet /></main>
      </div>
      <UpgradeDialog />
    </div>
  );
}
