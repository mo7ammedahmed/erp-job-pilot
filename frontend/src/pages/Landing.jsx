import { Link } from "react-router-dom";
import { Compass, ShieldCheck, Sparkles, KanbanSquare, BellRing, Mail, ArrowRight, Languages, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";

const HERO = "https://images.unsplash.com/photo-1694018359679-49465b4c0d61?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400";
const FEATURES = [
  [Sparkles, "AI job review", "Match score, missing skills, red flags and a clear Apply / Maybe / Skip verdict for every job."],
  [ShieldCheck, "Tailored CVs, never invented", "Every tailored CV is checked against your master CV. Anything not in it is flagged before you approve."],
  [KanbanSquare, "One tracker for everything", "Kanban from Saved to Offer with notes, contacts, documents and a full timeline."],
  [BellRing, "Reminders that respect you", "Follow-ups, interview prep and deadlines — in your timezone, outside your quiet hours."],
  [Mail, "Send from your own Gmail", "Drafts and applications with your approved CV attached. Nothing is ever sent without you."],
  [Languages, "Arabic & English", "Fully mirrored Arabic interface and ATS-ready CVs in either language."],
];

export default function Landing() {
  const { t, lang, setLang } = useI18n();
  const { user } = useAuth();
  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <header className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-5">
        <div className="flex items-center gap-2"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900 text-white"><Compass className="h-4 w-4" /></div><span className="font-heading text-lg font-bold">JobPilot</span></div>
        <div className="ms-auto flex items-center gap-2">
          <button data-testid="landing-language-toggle" onClick={() => setLang(lang === "ar" ? "en" : "ar")} className="rounded-lg px-3 py-2 text-sm hover:bg-slate-100">{lang === "ar" ? "English" : "العربية"}</button>
          {user ? <Link to="/app"><Button data-testid="landing-open-app" className="bg-emerald-900 hover:bg-emerald-800">{t("Open app")}</Button></Link> : <>
            <Link to="/login" data-testid="landing-login-link" className="rounded-lg px-3 py-2 text-sm font-medium hover:bg-slate-100">{t("Log in")}</Link>
            <Link to="/register"><Button data-testid="landing-get-started" className="bg-emerald-900 hover:bg-emerald-800">{t("Get started free")}</Button></Link></>}
        </div>
      </header>
      <section className="mx-auto grid max-w-7xl gap-10 px-5 pb-16 pt-8 lg:grid-cols-12 lg:pt-14">
        <div className="lg:col-span-6 jp-rise">
          <div className="jp-eyebrow mb-4">{t("The ERP for job seekers · Saudi Arabia & GCC")}</div>
          <h1 className="font-heading text-4xl font-bold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">{t("Run your job search like a project, not a lottery.")}</h1>
          <p className="mt-6 max-w-xl text-base text-slate-600 md:text-lg">{t("JobPilot collects jobs from legal sources, scores each one against your real CV, tailors an honest ATS-ready CV, and keeps every application and follow-up on track.")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register"><Button size="lg" data-testid="hero-cta" className="bg-emerald-900 hover:bg-emerald-800">{t("Start free")} <ArrowRight className="ms-2 h-4 w-4 rtl:rotate-180" /></Button></Link>
            <Link to="/login"><Button size="lg" variant="outline" data-testid="hero-login">{t("I have an account")}</Button></Link>
          </div>
          <ul className="mt-8 space-y-2 text-sm text-slate-600">
            {["No scraping — official APIs and company feeds only", "You approve everything before it's sent", "PDPL & GDPR-ready: export or delete anytime"].map((s) => (
              <li key={s} className="flex items-center gap-2"><CheckCircle2 className="h-4 w-4 text-emerald-700" />{t(s)}</li>))}
          </ul>
        </div>
        <div className="relative lg:col-span-6 jp-rise-2">
          <img src={HERO} alt="Riyadh skyline" className="h-[420px] w-full rounded-2xl object-cover" />
          <div className="absolute bottom-5 start-5 end-5 rounded-xl border border-white/40 bg-white/85 p-4 backdrop-blur-xl sm:end-auto sm:w-80">
            <div className="flex items-center justify-between"><div><div className="text-sm font-semibold">Senior Data Analyst</div><div className="text-xs text-slate-500">Riyadh · Hybrid</div></div>
              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/15 px-2 py-1 font-mono text-sm font-bold text-emerald-800">86</div></div>
            <div className="mt-3 flex flex-wrap gap-1">{["SQL", "Power BI", "Python"].map((s) => <span key={s} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-800">{s}</span>)}
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800">{t("missing")}: Arabic</span></div>
          </div>
        </div>
      </section>
      <section className="border-t border-slate-200 bg-white py-16">
        <div className="mx-auto grid max-w-7xl gap-5 px-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([Icon, title, text], i) => (
            <div key={title} className={`rounded-xl border border-slate-200 p-6 jp-card-hover ${i === 1 ? "lg:row-span-1 bg-emerald-950 text-white border-emerald-900" : ""}`}>
              <Icon className={`h-5 w-5 ${i === 1 ? "text-emerald-300" : "text-emerald-800"}`} />
              <div className="mt-4 font-heading text-lg font-semibold">{t(title)}</div>
              <p className={`mt-2 text-sm ${i === 1 ? "text-emerald-100" : "text-slate-600"}`}>{t(text)}</p>
            </div>))}
        </div>
      </section>
      <footer className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-5 py-8 text-sm text-slate-500">
        <span>© 2026 JobPilot</span>
        <Link to="/legal/privacy" data-testid="footer-privacy" className="hover:text-slate-900">{t("Privacy policy")}</Link>
        <Link to="/legal/terms" data-testid="footer-terms" className="hover:text-slate-900">{t("Terms")}</Link>
      </footer>
    </div>
  );
}
