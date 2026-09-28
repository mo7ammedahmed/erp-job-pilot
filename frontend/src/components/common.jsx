import { Loader2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export const tier = (s) => (s == null ? "none" : s >= 75 ? "high" : s >= 50 ? "mid" : "low");
const TIER_CLS = {
  high: "bg-emerald-500/15 text-emerald-800 border-emerald-500/30",
  mid: "bg-amber-500/15 text-amber-800 border-amber-500/30",
  low: "bg-rose-500/15 text-rose-700 border-rose-500/30",
  none: "bg-slate-100 text-slate-500 border-slate-200",
};
const VERDICT = { apply: "Apply", maybe: "Maybe", skip: "Skip" };

export function ScoreBadge({ score, quick, testid }) {
  const { t } = useI18n();
  const cls = TIER_CLS[tier(score)];
  return (
    <div data-testid={testid} className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs font-semibold ${cls}`}>
      <span className="text-base leading-none">{score ?? "—"}</span>
      <span className="opacity-70">{quick ? t("quick") : "/100"}</span>
    </div>
  );
}

export function VerdictPill({ verdict, testid }) {
  const { t } = useI18n();
  if (!verdict) return null;
  const cls = { apply: TIER_CLS.high, maybe: TIER_CLS.mid, skip: TIER_CLS.low }[verdict];
  return (
    <span data-testid={testid} className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {t(VERDICT[verdict])}
    </span>
  );
}

export function ScoreRing({ score, size = 96 }) {
  const r = 40, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(100, score || 0));
  const color = { high: "#059669", mid: "#D97706", low: "#E11D48", none: "#CBD5E1" }[tier(score)];
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" data-testid="score-ring">
      <circle cx="50" cy="50" r={r} stroke="#E2E8F0" strokeWidth="9" fill="none" />
      <circle cx="50" cy="50" r={r} stroke={color} strokeWidth="9" fill="none" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={c - (c * pct) / 100} transform="rotate(-90 50 50)" style={{ transition: "stroke-dashoffset .8s ease" }} />
      <text x="50" y="57" textAnchor="middle" className="font-mono" fontSize="24" fontWeight="700" fill="#0F172A">{score ?? "—"}</text>
    </svg>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between jp-rise">
      <div>
        {eyebrow && <div className="jp-eyebrow mb-1">{eyebrow}</div>}
        <h1 className="font-heading text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ icon: Icon, title, text, action, testid }) {
  return (
    <div data-testid={testid} className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-slate-300 bg-white p-8">
      {Icon && <Icon className="h-6 w-6 text-emerald-800" />}
      <div className="font-heading text-lg font-semibold">{title}</div>
      {text && <p className="max-w-md text-sm text-slate-500">{text}</p>}
      {action}
    </div>
  );
}

export const Spinner = ({ className = "" }) => <Loader2 className={`h-4 w-4 animate-spin ${className}`} />;

export function FullLoader() {
  return <div className="flex min-h-[50vh] items-center justify-center"><Spinner className="h-6 w-6 text-emerald-800" /></div>;
}

export function Meter({ label, used, limit, testid }) {
  const { t, fmtNum } = useI18n();
  const unlimited = limit < 0;
  const pct = unlimited ? 8 : Math.min(100, Math.round((100 * used) / Math.max(limit, 1)));
  const bar = pct >= 90 ? "bg-rose-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-700";
  return (
    <div data-testid={testid} className="space-y-1.5">
      <div className="flex justify-between text-xs"><span className="text-slate-600">{label}</span>
        <span className="font-mono text-slate-900">{fmtNum(used)} / {unlimited ? "∞" : fmtNum(limit)}</span></div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${bar}`} style={{ width: `${pct}%` }} /></div>
      {!unlimited && pct >= 100 && <div className="text-xs text-rose-600">{t("Limit reached")}</div>}
    </div>
  );
}

export function Card({ children, className = "", ...p }) {
  return <div className={`rounded-xl border border-slate-200 bg-white p-5 ${className}`} {...p}>{children}</div>;
}
