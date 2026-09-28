import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Search, Plus, RefreshCw, MapPin, Bookmark, X, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { COUNTRIES, CITIES, countryName } from "@/lib/constants";
import { PageHeader, ScoreBadge, VerdictPill, Empty, Spinner, FullLoader } from "@/components/common";
import { SimpleSelect, Field } from "@/pages/Onboarding";

const ANY = "any";

function JobCard({ j }) {
  const { t, fmtDate, lang, fmtNum } = useI18n();
  return (
    <Link to={`/app/jobs/${j.job_id}`} data-testid={`job-card-${j.job_id}`} className="block rounded-xl border border-slate-200 bg-white p-4 jp-card-hover">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="truncate font-heading font-semibold text-slate-900">{j.title}</div>
          <div className="mt-0.5 text-sm text-slate-600">{j.company || "—"}</div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{j.location || countryName(j.country, lang) || "—"}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 capitalize">{t(j.remote)}</span>
            {j.salary_max && <span className="font-mono text-emerald-800">{fmtNum(j.salary_min || j.salary_max)}–{fmtNum(j.salary_max)} {j.currency}</span>}
            <span className="font-mono">{(j.sources || []).join(" · ")}</span>
            {j.posted_at && <span>{fmtDate(j.posted_at)}</span>}
          </div>
          <p className="mt-2 line-clamp-2 text-sm text-slate-500">{j.snippet}</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {j.review ? <><ScoreBadge score={j.review.score} testid="job-card-score" /><VerdictPill verdict={j.review.verdict} /></> :
            j.quick_score != null ? <ScoreBadge score={j.quick_score} quick testid="job-card-quick-score" /> : null}
        </div>
      </div>
    </Link>
  );
}

function ManualDialog({ open, onClose, initial }) {
  const { t } = useI18n();
  const nav = useNavigate();
  const [f, setF] = useState({ text: "", url: "" });
  useEffect(() => { if (initial) setF(initial); }, [initial]);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/jobs/manual", f);
      toast.success(t("Job added"));
      nav(`/app/jobs/${data.job_id}`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl bg-white">
        <DialogHeader><DialogTitle>{t("Add a job manually")}</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">{t("Paste the job description from LinkedIn, Bayt, a company site or anywhere else. JobPilot never crawls those sites.")}</p>
        <Input data-testid="manual-job-url" placeholder={t("Job link (optional)")} value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
        <Textarea data-testid="manual-job-text" rows={10} placeholder={t("Paste the full job description")} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} />
        <Button data-testid="manual-job-submit" disabled={busy || f.text.length < 40} onClick={submit} className="bg-emerald-900 hover:bg-emerald-800">{busy && <Spinner className="me-2" />}{t("Add job")}</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function Jobs() {
  const { t, lang, fmtNum } = useI18n();
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const init = { keywords: "", country: user?.country || "SA", city: "", remote: ANY, seniority: "", min_salary: "", source: ANY, verdict: ANY };
  const [f, setF] = useState(init);
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [searches, setSearches] = useState([]);
  const [sources, setSources] = useState([]);
  const [manual, setManual] = useState(!!sp.get("add_text"));
  const prefill = sp.get("add_text") ? { text: sp.get("add_text") || "", url: sp.get("add_url") || "" } : null;
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [alerts, setAlerts] = useState(true);
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }));
  const params = (ff, p) => Object.fromEntries(Object.entries({ ...ff, page: p }).filter(([, v]) => v !== "" && v !== ANY));
  const load = useCallback(async (ff, p = 1) => {
    const { data: d } = await api.get("/jobs", { params: params(ff, p) });
    setData((prev) => (p > 1 && prev ? { ...d, items: [...prev.items, ...d.items] } : d));
    setPage(p);
  }, []);
  const loadSearches = () => api.get("/searches").then((r) => setSearches(r.data));
  useEffect(() => {
    loadSearches();
    api.get("/meta/sources").then((r) => setSources(r.data));
    const sid = sp.get("search");
    if (!sid) load(init);
  }, []); // eslint-disable-line
  useEffect(() => {
    const sid = sp.get("search");
    const s = searches.find((x) => x.search_id === sid);
    if (s) applySearch(s);
  }, [searches]); // eslint-disable-line
  const applySearch = (s) => {
    const ff = { ...init, keywords: s.keywords, country: s.country, city: s.city, remote: s.remote || ANY, seniority: s.seniority, min_salary: s.min_salary || "" };
    setF(ff);
    load(ff);
  };
  const saveSearch = async () => {
    try {
      await api.post("/searches", { name: saveName, keywords: f.keywords, country: f.country, city: f.city, remote: f.remote === ANY ? "" : f.remote,
        seniority: f.seniority, min_salary: f.min_salary ? Number(f.min_salary) : null, alerts });
      toast.success(t("Search saved"));
      setSaveOpen(false); setSaveName(""); loadSearches();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const refresh = async () => {
    const { data: r } = await api.post("/jobs/refresh");
    toast(r.started ? t("Fetching new jobs in the background…") : t(r.message));
  };
  return (
    <div>
      <PageHeader eyebrow={t("Job feed")} title={t("Jobs for you")} subtitle={data ? t("{n} jobs match your filters", { n: fmtNum(data.total) }) : ""}
        actions={<>
          <Button variant="outline" onClick={refresh} data-testid="jobs-refresh-button"><RefreshCw className="me-2 h-4 w-4" />{t("Fetch new")}</Button>
          <Button onClick={() => setManual(true)} className="bg-emerald-900 hover:bg-emerald-800" data-testid="jobs-add-manual-button"><Plus className="me-2 h-4 w-4" />{t("Add job")}</Button></>} />
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-4">
          <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
            <Field label={t("Keywords")}><Input data-testid="filter-keywords" placeholder={t("e.g. data analyst, SQL")} value={f.keywords} onChange={(e) => set("keywords")(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(f)} /></Field>
            <Field label={t("Country")}><SimpleSelect testid="filter-country" value={f.country} onChange={set("country")} options={COUNTRIES.map((x) => [x[0], lang === "ar" ? x[2] : x[1]])} /></Field>
            <Field label={t("City")}>
              <Input data-testid="filter-city" list="city-suggestions" value={f.city} onChange={(e) => set("city")(e.target.value)} placeholder={t("e.g. Riyadh")} />
              <datalist id="city-suggestions">{(CITIES[f.country] || []).map(([k, en, ar]) => <option key={k} value={lang === "ar" ? ar : en} />)}</datalist>
            </Field>
            <Field label={t("Work mode")}><SimpleSelect testid="filter-remote" value={f.remote} onChange={set("remote")} options={[[ANY, t("Any")], ["remote", t("remote")], ["onsite", t("onsite")], ["hybrid", t("hybrid")]]} /></Field>
            <Field label={t("Seniority")}><SimpleSelect testid="filter-seniority" value={f.seniority || ANY} onChange={(v) => set("seniority")(v === ANY ? "" : v)} options={[[ANY, t("Any")], ["junior", t("Junior")], ["senior", t("Senior")], ["lead", t("Lead")], ["manager", t("Manager")], ["director", t("Director")]]} /></Field>
            <Field label={t("Minimum salary")}><Input data-testid="filter-min-salary" type="number" value={f.min_salary} onChange={(e) => set("min_salary")(e.target.value)} /></Field>
            <Field label={t("Source")}><SimpleSelect testid="filter-source" value={f.source} onChange={set("source")} options={[[ANY, t("Any")], ...sources.map((s) => [s.source_id, s.name]), ["manual", t("Added by me")]]} /></Field>
            <Field label={t("AI verdict")}><SimpleSelect testid="filter-verdict" value={f.verdict} onChange={set("verdict")} options={[[ANY, t("Any")], ["apply", t("Apply")], ["maybe", t("Maybe")], ["skip", t("Skip")]]} /></Field>
            <div className="flex gap-2 pt-1">
              <Button data-testid="filter-apply-button" onClick={() => load(f)} className="flex-1 bg-emerald-900 hover:bg-emerald-800"><Search className="me-2 h-4 w-4" />{t("Search")}</Button>
              <Button data-testid="save-search-button" variant="outline" onClick={() => setSaveOpen(true)} title={t("Save search")}><Bookmark className="h-4 w-4" /></Button>
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="saved-searches">
            <div className="jp-eyebrow mb-2">{t("Saved searches")}</div>
            {searches.length === 0 && <p className="text-xs text-slate-500">{t("Save a search to get new-match alerts.")}</p>}
            {searches.map((s) => (
              <div key={s.search_id} className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50">
                <button className="flex-1 truncate text-start text-sm" onClick={() => applySearch(s)} data-testid={`saved-search-${s.search_id}`}>{s.name}</button>
                {s.alerts && <Bell className="h-3 w-3 text-emerald-700" />}
                <button onClick={() => api.delete(`/searches/${s.search_id}`).then(loadSearches)} className="opacity-0 group-hover:opacity-100"><X className="h-3.5 w-3.5 text-slate-400" /></button>
              </div>))}
          </div>
        </aside>
        <section className="space-y-3">
          {!data ? <FullLoader /> : data.items.length === 0 ? <Empty testid="jobs-empty" icon={Search} title={t("No jobs match yet")} text={t("Try fewer filters, press “Fetch new”, or add a job manually.")} /> :
            data.items.map((j) => <JobCard key={j.job_id} j={j} />)}
          {data && data.items.length < data.total && <Button variant="outline" className="w-full" onClick={() => load(f, page + 1)} data-testid="jobs-load-more">{t("Load more")}</Button>}
          <p className="pt-2 text-xs text-slate-400">{t("Listings via official APIs and public career feeds:")} {sources.filter((s) => s.enabled).map((s) => s.attribution).join(" · ")}</p>
        </section>
      </div>
      <ManualDialog open={manual} onClose={() => setManual(false)} initial={prefill} />
      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent className="bg-white">
          <DialogHeader><DialogTitle>{t("Save search")}</DialogTitle></DialogHeader>
          <Input data-testid="save-search-name" placeholder={t("Name, e.g. Riyadh data roles")} value={saveName} onChange={(e) => setSaveName(e.target.value)} />
          <label className="flex items-center gap-3 text-sm"><Switch checked={alerts} onCheckedChange={setAlerts} data-testid="save-search-alerts" />{t("Alert me about new matches")}</label>
          <Button data-testid="save-search-submit" disabled={!saveName} onClick={saveSearch} className="bg-emerald-900 hover:bg-emerald-800">{t("Save")}</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
