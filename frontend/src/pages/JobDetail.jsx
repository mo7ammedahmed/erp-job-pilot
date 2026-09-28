import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, ExternalLink, BookmarkPlus, Wand2, AlertTriangle, ArrowLeft, CheckCircle2, Banknote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { countryName, STATUS_LABEL } from "@/lib/constants";
import { Card, FullLoader, ScoreRing, VerdictPill, Spinner, ScoreBadge } from "@/components/common";
import { SimpleSelect } from "@/pages/Onboarding";

const Chips = ({ items, cls, testid }) => (
  <div className="flex flex-wrap gap-1.5" data-testid={testid}>{(items || []).map((s, i) => <span key={i} className={`rounded-md px-2 py-0.5 text-xs ${cls}`}>{s}</span>)}</div>
);

function ReviewPanel({ review }) {
  const { t } = useI18n();
  const r = review.result;
  return (
    <div className="space-y-5" data-testid="review-panel">
      <div className="flex items-center gap-5">
        <ScoreRing score={r.score} />
        <div><VerdictPill verdict={r.verdict} testid="review-verdict" /><p className="mt-2 text-sm text-slate-700">{r.summary}</p>
          <p className="mt-1 font-mono text-[10px] text-slate-400">{review.model} · {review.prompt_version}</p></div>
      </div>
      <div><div className="jp-eyebrow mb-2">{t("Matched skills")}</div><Chips testid="review-matched" items={r.matched_skills} cls="bg-emerald-50 text-emerald-800 border border-emerald-200" /></div>
      <div><div className="jp-eyebrow mb-2">{t("Missing skills")}</div><Chips testid="review-missing" items={r.missing_skills} cls="bg-amber-50 text-amber-800 border border-amber-200" /></div>
      {r.keyword_gaps?.length > 0 && <div><div className="jp-eyebrow mb-2">{t("Keyword gaps")}</div><Chips items={r.keyword_gaps} cls="bg-slate-100 text-slate-700" /></div>}
      {r.red_flags?.length > 0 && <div className="space-y-2" data-testid="review-red-flags">{r.red_flags.map((f, i) => (
        <div key={i} className="flex gap-2 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{f}</div>))}</div>}
      <div className="grid gap-2 text-sm">{Object.entries(r.notes || {}).filter(([, v]) => v).map(([k, v]) => (
        <div key={k} className="rounded-lg bg-slate-50 p-2.5"><span className="font-semibold capitalize">{t(k)}: </span>{v}</div>))}</div>
      <div><div className="jp-eyebrow mb-2">{t("Why")}</div><ul className="space-y-1.5 text-sm">{(r.reasons || []).map((x, i) => <li key={i} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-700" />{x}</li>)}</ul></div>
    </div>
  );
}

function SalaryCard({ jobId }) {
  const { t, fmtNum } = useI18n();
  const [s, setS] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => { api.get(`/jobs/${jobId}/salary`).then((r) => setS(r.data)).catch(() => setErr(true)); }, [jobId]);
  if (err) return null;
  return (
    <Card className="jp-rise-3" data-testid="salary-card">
      <div className="mb-3 flex items-center gap-2 font-heading font-semibold"><Banknote className="h-4 w-4 text-emerald-800" />{t("Salary benchmark")}</div>
      {!s ? <Spinner /> : s.median == null ? (
        <p className="text-sm text-slate-500" data-testid="salary-unavailable">
          {s.notes || t("No salary benchmark is available for this role yet.")}
        </p>
      ) : <>
        <div className="font-mono text-2xl font-semibold text-slate-900" data-testid="salary-median">{fmtNum(s.median)} <span className="text-sm text-slate-500">{s.currency}{s.period === "month" ? ` / ${t("mo")}` : ""}</span></div>
        <div className="mt-2 h-2 rounded-full bg-gradient-to-r from-emerald-100 via-emerald-500 to-emerald-100" />
        <div className="mt-1 flex justify-between font-mono text-xs text-slate-500"><span>P25 {fmtNum(s.p25)}</span><span>P75 {fmtNum(s.p75)}</span></div>
        <p className="mt-3 text-xs text-slate-500">{s.source === "listings" ? t("Based on {n} listings with published salaries.", { n: s.sample_size }) : t("AI estimate (confidence: {c}). Verify with the employer.", { c: t(s.confidence || "low") })} {s.notes}</p>
      </>}
    </Card>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  const { t, lang, fmtDate, fmtNum } = useI18n();
  const { user } = useAuth();
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");
  const [tlLang, setTlLang] = useState(user?.lang || "en");
  const load = () => api.get(`/jobs/${id}`).then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [id]); // eslint-disable-line
  const act = async (name, fn) => {
    setBusy(name);
    try { await fn(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  if (!d) return <FullLoader />;
  const j = d.job;
  const review = () => act("review", async () => { await api.post(`/jobs/${id}/review`, { force: false }); await load(); });
  const save = () => act("save", async () => { await api.post("/applications", { job_id: id, status: "saved" }); toast.success(t("Saved to tracker")); await load(); });
  const tailor = () => act("tailor", async () => {
    const { data } = await api.post("/tailor", { job_id: id, application_id: d.application?.application_id, lang: tlLang });
    nav(`/app/tailor/${data.tailored_id}`);
  });
  return (
    <div>
      <Link to="/app/jobs" className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft className="h-4 w-4 rtl:rotate-180" />{t("Back to jobs")}</Link>
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <Card className="jp-rise">
            <div className="flex flex-wrap items-start gap-4">
              <div className="min-w-0 flex-1">
                <h1 className="font-heading text-2xl font-bold tracking-tight" data-testid="job-title">{j.title}</h1>
                <div className="mt-1 text-slate-600">{j.company}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span className="rounded bg-slate-100 px-2 py-1">{j.location || countryName(j.country, lang)}</span>
                  <span className="rounded bg-slate-100 px-2 py-1 capitalize">{t(j.remote)}</span>
                  {j.salary_max && <span className="rounded bg-emerald-50 px-2 py-1 font-mono text-emerald-800">{fmtNum(j.salary_min || j.salary_max)}–{fmtNum(j.salary_max)} {j.currency}</span>}
                  <span className="rounded bg-slate-100 px-2 py-1 font-mono">{(j.sources || []).join(" · ")}</span>
                  {j.posted_at && <span className="px-1 py-1">{fmtDate(j.posted_at)}</span>}
                </div>
              </div>
              {d.quick_score != null && !d.review && <ScoreBadge score={d.quick_score} quick />}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {d.application ? <Link to={`/app/tracker?app=${d.application.application_id}`}><Button variant="outline" data-testid="job-open-application">{t("In tracker")}: {t(STATUS_LABEL[d.application.status])}</Button></Link> :
                <Button variant="outline" onClick={save} disabled={!!busy} data-testid="job-save-button">{busy === "save" ? <Spinner className="me-2" /> : <BookmarkPlus className="me-2 h-4 w-4" />}{t("Save to tracker")}</Button>}
              {j.url && <a href={j.url} target="_blank" rel="noreferrer"><Button variant="ghost" data-testid="job-original-link"><ExternalLink className="me-2 h-4 w-4" />{t("View original")}</Button></a>}
            </div>
          </Card>
          <Card><div className="jp-eyebrow mb-3">{t("Job description")}</div><div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700" data-testid="job-description">{j.description}</div></Card>
        </div>
        <aside className="space-y-4">
          <Card className="jp-rise-2">
            <div className="mb-4 flex items-center gap-2 font-heading font-semibold"><Sparkles className="h-4 w-4 text-emerald-800" />{t("AI review")}</div>
            {!d.has_master ? <div className="text-sm text-slate-600">{t("Upload your master CV first.")} <Link to="/app/cv" className="text-emerald-800 underline">{t("CV vault")}</Link></div> :
              d.review ? <ReviewPanel review={d.review} /> :
                <Button className="w-full bg-emerald-900 hover:bg-emerald-800" onClick={review} disabled={!!busy} data-testid="run-review-button">{busy === "review" ? <Spinner className="me-2" /> : <Sparkles className="me-2 h-4 w-4" />}{busy === "review" ? t("Reviewing…") : t("Run AI review")}</Button>}
          </Card>
          {d.has_master && <Card className="jp-rise-3">
            <div className="mb-3 flex items-center gap-2 font-heading font-semibold"><Wand2 className="h-4 w-4 text-emerald-800" />{t("Tailor CV & cover letter")}</div>
            <p className="mb-3 text-xs text-slate-500">{t("Only reorders and rephrases your real experience. Every claim is checked against your master CV.")}</p>
            <div className="flex gap-2"><div className="w-32"><SimpleSelect testid="tailor-lang-select" value={tlLang} onChange={setTlLang} options={[["en", "English"], ["ar", "العربية"]]} /></div>
              <Button className="flex-1 bg-emerald-900 hover:bg-emerald-800" onClick={tailor} disabled={!!busy} data-testid="tailor-button">{busy === "tailor" ? <><Spinner className="me-2" />{t("Writing…")}</> : t("Tailor")}</Button></div>
            {d.tailored.length > 0 && <ul className="mt-4 space-y-1 border-t pt-3 text-sm">{d.tailored.map((x) => (
              <li key={x.tailored_id}><Link to={`/app/tailor/${x.tailored_id}`} className="flex justify-between hover:underline"><span>{x.lang.toUpperCase()} · {t(x.status)}</span><span className="text-xs text-slate-400">{fmtDate(x.created_at)}</span></Link></li>))}</ul>}
          </Card>}
          <SalaryCard jobId={id} />
        </aside>
      </div>
    </div>
  );
}
