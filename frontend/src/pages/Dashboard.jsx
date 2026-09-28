import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Target, TrendingUp, CalendarClock, Ghost, FileText, Briefcase } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Card, FullLoader, ScoreBadge, VerdictPill, Empty } from "@/components/common";
import { Button } from "@/components/ui/button";
import { STATUS_LABEL } from "@/lib/constants";

function Kpi({ label, value, sub, testid }) {
  return (
    <Card className="jp-rise" data-testid={testid}>
      <div className="jp-eyebrow">{label}</div>
      <div className="mt-2 font-mono text-3xl font-semibold text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </Card>
  );
}

export default function Dashboard() {
  const { t, fmtDateTime, fmtNum } = useI18n();
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [hasCV, setHasCV] = useState(true);
  useEffect(() => {
    api.get("/dashboard").then((r) => setD(r.data));
    api.get("/cv").then((r) => setHasCV(!!r.data.master));
  }, []);
  if (!d) return <FullLoader />;
  const max = Math.max(1, ...d.funnel.map((f) => f.count));
  const wk = d.weekly;
  return (
    <div>
      <PageHeader eyebrow={t("Dashboard")} title={t("Hello, {name}", { name: user?.name?.split(" ")[0] || "" })} subtitle={t("Here's where your job search stands this week.")}
        actions={<Link to="/app/jobs"><Button className="bg-emerald-900 hover:bg-emerald-800" data-testid="dash-browse-jobs"><Briefcase className="me-2 h-4 w-4" />{t("Browse jobs")}</Button></Link>} />
      {!hasCV && <Card className="mb-6 flex flex-col items-start gap-3 border-amber-200 bg-amber-50 sm:flex-row sm:items-center" data-testid="dash-cv-nudge">
        <FileText className="h-5 w-5 text-amber-700" /><div className="flex-1 text-sm text-amber-900">{t("Upload your CV to unlock AI reviews and tailored CVs.")}</div>
        <Link to="/app/cv"><Button size="sm" variant="outline">{t("Upload CV")}</Button></Link></Card>}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi testid="kpi-applied" label={t("Applied")} value={fmtNum(d.funnel[1].count)} sub={t("{n} tracked in total", { n: d.funnel[0].count })} />
        <Kpi testid="kpi-response-rate" label={t("Response rate")} value={`${fmtNum(d.response_rate)}%`} />
        <Kpi testid="kpi-interview-rate" label={t("Interview rate")} value={`${fmtNum(d.interview_rate)}%`} />
        <Card className="jp-rise" data-testid="kpi-weekly-goal">
          <div className="jp-eyebrow flex items-center gap-1"><Target className="h-3 w-3" />{t("Weekly goal")}</div>
          <div className="mt-2 font-mono text-3xl font-semibold">{fmtNum(wk.done)}<span className="text-lg text-slate-400">/{fmtNum(wk.goal)}</span></div>
          <div className="mt-2 h-1.5 rounded-full bg-slate-100"><div className="h-full rounded-full bg-emerald-700" style={{ width: `${Math.min(100, (100 * wk.done) / wk.goal)}%` }} /></div>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-4">
        <Card className="lg:col-span-2 jp-rise-2" data-testid="dash-funnel">
          <div className="mb-4 flex items-center gap-2 font-heading font-semibold"><TrendingUp className="h-4 w-4 text-emerald-800" />{t("Funnel")}</div>
          <div className="space-y-3">{d.funnel.map((f) => (
            <div key={f.stage} className="grid grid-cols-[90px_1fr_40px] items-center gap-3 text-sm">
              <span className="text-slate-600">{t(STATUS_LABEL[f.stage])}</span>
              <div className="h-6 rounded bg-slate-100"><div className="h-full rounded bg-emerald-800/90" style={{ width: `${(100 * f.count) / max}%`, transition: "width .6s" }} /></div>
              <span className="text-end font-mono">{fmtNum(f.count)}</span></div>))}</div>
        </Card>
        <Card className="lg:col-span-2 jp-rise-2" data-testid="dash-upcoming">
          <div className="mb-4 flex items-center gap-2 font-heading font-semibold"><CalendarClock className="h-4 w-4 text-emerald-800" />{t("Coming up")}</div>
          {d.upcoming_interviews.length + d.reminders.length === 0 && <p className="text-sm text-slate-500">{t("No interviews or reminders scheduled.")}</p>}
          <ul className="divide-y">{d.upcoming_interviews.map((a) => (
            <li key={a.application_id} className="flex justify-between py-2 text-sm"><Link className="hover:underline" to={`/app/tracker?app=${a.application_id}`}>{t("Interview")}: {a.title} · {a.company}</Link><span className="font-mono text-xs text-amber-700">{fmtDateTime(a.interview_at)}</span></li>))}
            {d.reminders.map((r) => <li key={r.reminder_id} className="flex justify-between py-2 text-sm"><span>{r.title}</span><span className="font-mono text-xs text-slate-500">{fmtDateTime(r.due_at)}</span></li>)}</ul>
        </Card>
        <Card className="lg:col-span-2 jp-rise-3" data-testid="dash-sources">
          <div className="mb-3 font-heading font-semibold">{t("Best sources")}</div>
          {d.sources.length === 0 ? <p className="text-sm text-slate-500">{t("Apply to a few jobs to see which sources work best.")}</p> :
            <table className="w-full text-sm"><thead><tr className="text-start text-xs text-slate-500"><th className="text-start font-normal">{t("Source")}</th><th className="text-end font-normal">{t("Applied")}</th><th className="text-end font-normal">{t("Interviews")}</th></tr></thead>
              <tbody>{d.sources.map((s) => <tr key={s.source} className="border-t"><td className="py-2 capitalize">{s.source}</td><td className="text-end font-mono">{fmtNum(s.applied)}</td><td className="text-end font-mono">{fmtNum(s.interviews)}</td></tr>)}</tbody></table>}
        </Card>
        <Card className="lg:col-span-2 jp-rise-3" data-testid="dash-recent-reviews">
          <div className="mb-3 font-heading font-semibold">{t("Recent AI reviews")}</div>
          {d.recent_reviews.length === 0 ? <Empty title={t("No reviews yet")} text={t("Open a job and run an AI review.")} /> :
            <ul className="divide-y">{d.recent_reviews.map((r) => (
              <li key={r.job_id} className="flex items-center gap-3 py-2"><ScoreBadge score={r.result?.score} /><Link to={`/app/jobs/${r.job_id}`} className="flex-1 truncate text-sm hover:underline">{r.title} · {r.company}</Link><VerdictPill verdict={r.result?.verdict} /></li>))}</ul>}
        </Card>
      </div>
      {d.ghost_suggestions.length > 0 && <Card className="mt-4" data-testid="dash-ghost">
        <div className="mb-2 flex items-center gap-2 font-heading font-semibold"><Ghost className="h-4 w-4" />{t("No reply for a while")}</div>
        {d.ghost_suggestions.map((a) => <Link key={a.application_id} to={`/app/tracker?app=${a.application_id}`} className="block py-1 text-sm hover:underline">{a.title} · {a.company}</Link>)}</Card>}
    </div>
  );
}
