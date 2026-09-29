import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { PageHeader, Card, FullLoader, Spinner } from "@/components/common";
import { SimpleSelect } from "@/pages/Onboarding";

const Th = ({ cols }) => <thead className="bg-slate-50 text-xs text-slate-500"><tr>{cols.map((c) => <th key={c} className="px-3 py-2 text-start font-medium">{c}</th>)}</tr></thead>;

function Overview() {
  const [s, setS] = useState(null);
  const [ins, setIns] = useState(null);
  useEffect(() => { api.get("/admin/stats").then((r) => setS(r.data)); api.get("/admin/insights").then((r) => setIns(r.data)); }, []);
  if (!s) return <FullLoader />;
  return <div className="grid grid-cols-2 gap-4 lg:grid-cols-5" data-testid="admin-stats">{[["Users", s.users], ["Jobs", s.jobs], ["Applications", s.applications], ["AI calls 30d", s.ai_calls_30d], ["AI cost 30d", `$${s.ai_cost_30d}`]].map(([l, v]) => (
    <Card key={l}><div className="jp-eyebrow">{l}</div><div className="mt-2 font-mono text-2xl font-semibold">{v}</div></Card>))}
    <Card className="col-span-2 lg:col-span-5"><div className="jp-eyebrow mb-2">{t("Plans")}</div><div className="flex gap-6 font-mono text-sm">{Object.entries(s.plans).map(([k, v]) => <span key={k}>{k}: {v}</span>)}</div></Card>
    {ins && <Card className="col-span-2 lg:col-span-5" data-testid="admin-insights"><div className="jp-eyebrow mb-3">Anonymised insights · {ins.total_applied} applications</div>
      <div className="grid gap-6 md:grid-cols-2"><div><div className="mb-2 text-sm font-semibold">{t("Response rate by weekday applied")}</div>{ins.by_weekday.map((d) => (
        <div key={d.day} className="grid grid-cols-[40px_1fr_70px] items-center gap-2 py-0.5 text-xs"><span>{d.day}</span><div className="h-3 rounded bg-slate-100"><div className="h-full rounded bg-emerald-700" style={{ width: `${d.rate}%` }} /></div><span className="font-mono">{d.rate}% ({d.applied})</span></div>))}</div>
        <div><div className="mb-2 text-sm font-semibold">{t("Response rate by source")}</div>{ins.by_source.map((x) => <div key={x.source} className="flex justify-between border-t py-1 font-mono text-xs"><span>{x.source}</span><span>{x.rate}% {t("of")} {x.applied}</span></div>)}</div></div></Card>}</div>;
}

function GrantPlan({ u, patch }) {
  const [plan, setPlan] = useState("pro");
  const [days, setDays] = useState(30);
  if (u.role === "admin") return <span className="text-xs text-emerald-700">{t("Premium (admin)")}</span>;
  return (
    <div className="flex items-center gap-1">
      <div className="w-24"><SimpleSelect testid={`admin-grant-plan-${u.email}`} value={plan} onChange={setPlan} options={[["pro", "Pro"], ["premium", "Premium"]]} /></div>
      <Input className="h-9 w-16" type="number" min={1} value={days} onChange={(e) => setDays(+e.target.value)} data-testid={`admin-grant-days-${u.email}`} />
      <Button size="sm" variant="outline" onClick={() => patch(u.user_id, { plan, plan_days: days })} data-testid={`admin-grant-${u.email}`}>{t("days")}</Button>
    </div>
  );
}

function Users() {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState(null);
  const load = () => api.get("/admin/users", { params: { q } }).then((r) => setUsers(r.data));
  useEffect(() => { load(); }, []); // eslint-disable-line
  const patch = (id, body) => api.patch(`/admin/users/${id}`, body).then(load).catch((e) => toast.error(errMsg(e)));
  return (
      <Card className="p-0"><div className="flex gap-2 p-4"><Input data-testid="admin-user-search" placeholder={t("Search email or name")} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} /><Button onClick={load} variant="outline">{t("Search")}</Button></div>
      <div className="overflow-x-auto"><table className="w-full text-sm"><Th cols={["User", "Plan", "Grant for a period", "Usage (rev/tail/cv)", "AI $ month", "Role", "Suspended"]} />
        <tbody>{(users || []).map((u) => (
          <tr key={u.user_id} className="border-t" data-testid={`admin-user-${u.email}`}>
            <td className="px-3 py-2"><div className="font-medium">{u.name}</div><div className="text-xs text-slate-500">{u.email}</div></td>
            <td className="px-3 py-2 w-36">{u.role === "admin" ? <span className="font-mono text-xs">premium</span> : <SimpleSelect testid={`admin-plan-${u.email}`} value={u.plan} onChange={(v) => patch(u.user_id, { plan: v })} options={[["free", "Free"], ["pro", "Pro"], ["premium", "Premium"]]} />}
              {u.plan_expires_at && <div className="mt-1 font-mono text-[10px] text-amber-700" data-testid={`admin-plan-expiry-${u.email}`}>until {u.plan_expires_at.slice(0, 10)}</div>}</td>
            <td className="px-3 py-2"><GrantPlan u={u} patch={patch} /></td>
            <td className="px-3 py-2 font-mono text-xs">{u.usage.reviews}/{u.usage.tailors}/{u.usage.parses}</td>
            <td className="px-3 py-2 font-mono text-xs">${u.ai_cost_month}</td>
            <td className="px-3 py-2 text-xs">{u.role}</td>
            <td className="px-3 py-2"><Switch data-testid={`admin-suspend-${u.email}`} checked={!!u.suspended} onCheckedChange={(v) => patch(u.user_id, { suspended: v })} /></td></tr>))}</tbody></table></div></Card>
  );
}

function Plans() {
  const [plans, setPlans] = useState(null);
  const [trial, setTrial] = useState(null);
  useEffect(() => { api.get("/admin/plans").then((r) => setPlans(r.data)); api.get("/admin/trial").then((r) => setTrial(r.data)); }, []);
  if (!plans || !trial) return <FullLoader />;
  const saveTrial = () => api.put("/admin/trial", { plan: trial.plan, days: +trial.days }).then(() => toast.success("Trial saved")).catch((e) => toast.error(errMsg(e)));
  const trialCard = (
    <Card className="md:col-span-3 flex flex-wrap items-end gap-3" data-testid="admin-trial-card">
      <div className="flex-1 text-sm"><div className="font-heading font-semibold">{t("Free trial for new users")}</div><div className="text-xs text-slate-500">{t("New sign-ups get this plan for N days, then return to Free automatically. 0 = off.")}</div></div>
      <div className="w-32"><SimpleSelect testid="admin-trial-plan" value={trial.plan} onChange={(v) => setTrial({ ...trial, plan: v })} options={[["pro", "Pro"], ["premium", "Premium"]]} /></div>
      <Input className="w-24" type="number" min={0} max={365} value={trial.days} onChange={(e) => setTrial({ ...trial, days: e.target.value })} data-testid="admin-trial-days" />
      <Button onClick={saveTrial} className="bg-emerald-900 hover:bg-emerald-800" data-testid="admin-trial-save">{t("Save trial")}</Button>
    </Card>);
  const upd = (i, path, v) => setPlans(plans.map((p, j) => (j !== i ? p : path.length === 1 ? { ...p, [path[0]]: v } : { ...p, [path[0]]: { ...p[path[0]], [path[1]]: v } })));
  const save = (p) => api.put(`/admin/plans/${p.plan_id}`, { name: p.name, price_usd: +p.price_usd, price_sar: +p.price_sar, limits: p.limits, features: p.features }).then(() => toast.success("Plan saved")).catch((e) => toast.error(errMsg(e)));
  return <div className="grid gap-4 md:grid-cols-3">{trialCard}{plans.map((p, i) => (
    <Card key={p.plan_id} className="space-y-2" data-testid={`admin-plan-card-${p.plan_id}`}><Input value={p.name} onChange={(e) => upd(i, ["name"], e.target.value)} className="font-semibold" />
      <div className="grid grid-cols-2 gap-2"><label className="text-xs">USD<Input type="number" value={p.price_usd} onChange={(e) => upd(i, ["price_usd"], e.target.value)} /></label><label className="text-xs">SAR<Input type="number" value={p.price_sar} onChange={(e) => upd(i, ["price_sar"], e.target.value)} /></label></div>
      {Object.keys(p.limits).map((k) => <label key={k} className="flex items-center justify-between gap-2 text-xs">{k} (-1 = ∞)<Input className="w-24" type="number" value={p.limits[k]} onChange={(e) => upd(i, ["limits", k], +e.target.value)} data-testid={`admin-limit-${p.plan_id}-${k}`} /></label>)}
      {Object.keys(p.features).map((k) => <label key={k} className="flex items-center justify-between text-xs">{k}<Switch checked={p.features[k]} onCheckedChange={(v) => upd(i, ["features", k], v)} /></label>)}
      <Button size="sm" className="w-full bg-emerald-900 hover:bg-emerald-800" onClick={() => save(p)} data-testid={`admin-plan-save-${p.plan_id}`}>{t("Save")}</Button></Card>))}</div>;
}

function Sources() {
  const { fmtDateTime } = useI18n();
  const [items, setItems] = useState(null);
  const [probe, setProbe] = useState({});
  const [probing, setProbing] = useState("");
  const [keyDraft, setKeyDraft] = useState({});

  const [draft, setDraft] = useState({});
  const load = () => api.get("/admin/sources").then((r) => { setItems(r.data); setDraft({}); });
  useEffect(() => { load(); }, []);
  // Store or clear a deployment secret. The value is encrypted server-side and never sent back.
  const saveKey = async (key, value) => {
    setKeyDraft((d) => ({ ...d, [key]: "" }));
    try {
      await api.put("/admin/integrations/key", { key, value });
      await load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const patch = (id, body) => api.patch(`/admin/sources/${id}`, body).then(load);
  const run = async (id) => { const { data } = await api.post("/admin/sources/run", null, { params: { source_id: id } }); toast.success(`${data.new} new jobs`); load(); };
  // Board tokens are account slugs that cannot be guessed, so test them before saving.
  const testBoards = async (id, value) => {
    const boards = value.split(",").map((x) => x.trim()).filter(Boolean);
    if (!boards.length) { setProbe((p) => ({ ...p, [id]: [] })); return; }
    setProbing(id);
    try {
      const { data } = await api.post(`/admin/sources/${id}/probe`, { boards });
      setProbe((p) => ({ ...p, [id]: data.results }));
      const okCount = data.results.filter((r) => r.jobs > 0).length;
      const saCount = data.results.reduce((a, r) => a + (r.saudi || 0), 0);
      toast[okCount ? "success" : "error"](`${okCount}/${boards.length} boards respond · ${saCount} Saudi jobs`);
    } catch (e) { toast.error(errMsg(e)); } finally { setProbing(""); }
  };
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        {t("ATS boards are public employer job feeds. Paste the board tokens (the slug in the employer's careers URL, e.g. {url}), press Test to confirm they respond, then blur the field to save. Job counts show live coverage.").replace("{url}", "apply.workable.com/<board>")}
      </p>
      <Card className="overflow-x-auto p-0" data-testid="admin-sources"><table className="w-full text-sm"><Th cols={["Source", "Status", "Last run", "Fetched / new", "Jobs", "Boards", "On", ""]} />
      <tbody>{(items || []).map((s) => (
        <tr key={s.source_id} className="border-t align-top">
          <td className="px-3 py-2"><div className="font-medium">{s.name}</div><div className="text-xs text-slate-400">{s.kind}{s.env_key ? ` · ${Array.isArray(s.env_key) ? s.env_key.join(" + ") : s.env_key}` : ""}</div></td>
          <td className="px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-xs ${s.status === "ok" ? "bg-emerald-100 text-emerald-800" : s.status === "error" ? "bg-rose-100 text-rose-700" : "bg-slate-100"}`}>{s.status}</span>{s.last_error && <div className="mt-1 max-w-[200px] truncate text-xs text-rose-600" title={s.last_error}>{s.last_error}</div>}</td>
          <td className="px-3 py-2 font-mono text-xs">{s.last_run ? fmtDateTime(s.last_run) : "—"}</td>
          <td className="px-3 py-2 font-mono text-xs">{s.last_count ?? "—"} / {s.last_new ?? "—"}</td><td className="px-3 py-2 font-mono text-xs">{s.jobs}</td>
          <td className="px-3 py-2">{s.config?.boards ? (
            <div className="space-y-1">
              <div className="flex items-center gap-1">
                <Input className="h-8 w-40 text-xs" value={draft[s.source_id] ?? s.config.boards.join(", ")}
                  onChange={(e) => setDraft((d) => ({ ...d, [s.source_id]: e.target.value }))}
                  onBlur={() => {
                    const next = (draft[s.source_id] ?? s.config.boards.join(", "))
                      .split(",").map((x) => x.trim()).filter(Boolean);
                    if (next.join(",") !== s.config.boards.join(",")) patch(s.source_id, { config: { boards: next } });
                  }}
                  onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                  data-testid={`admin-boards-${s.source_id}`} />
                <Button size="sm" variant="outline" className="h-8 text-xs"
                  onClick={() => testBoards(s.source_id, draft[s.source_id] ?? s.config.boards.join(", "))}
                  // Keep focus in the field so clicking Test does not blur it and auto-save
                  // the half-typed list over the boards that are already configured.
                  onMouseDown={(e) => e.preventDefault()}
                  disabled={probing === s.source_id}
                  data-testid={`admin-boards-test-${s.source_id}`}>
                  {probing === s.source_id ? <Spinner className="h-3 w-3" /> : "Test"}
                </Button>
              </div>
              {probe[s.source_id]?.length > 0 && (
                <div className="max-w-40 text-[11px] leading-tight">
                  {probe[s.source_id].map((r) => (
                    <div key={r.board} className={r.jobs ? "text-emerald-700" : "text-slate-400"}>
                      {r.board}: {r.jobs}{r.saudi ? ` (${r.saudi} SA)` : ""}
                    </div>
                  ))}
                </div>
              )}
            </div>
            ) : s.needs_key ? (
              <div className="space-y-1">
                {s.keys.map((k) => (
                  <div key={k.key} className="flex items-center gap-1">
                    <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${k.set ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>{k.set ? "✓" : "○"} {k.key}</span>
                    <Input data-testid={`admin-source-key-${k.key}`} type="password" autoComplete="new-password"
                      className="h-8 w-32 text-xs" placeholder={k.set ? "••••••••" : "paste key"}
                      value={keyDraft[k.key] || ""}
                      onChange={(e) => setKeyDraft((d) => ({ ...d, [k.key]: e.target.value }))}
                      onBlur={() => (keyDraft[k.key] || "").trim() && saveKey(k.key, keyDraft[k.key])}
                      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }} />
                    {k.set && <Button size="sm" variant="ghost" className="h-8 px-1.5 text-xs"
                      onClick={() => saveKey(k.key, "")} data-testid={`admin-source-key-clear-${k.key}`}>{t("Clear")}</Button>}
                    {k.signup && <a href={k.signup} target="_blank" rel="noreferrer"
                      className="text-[11px] text-emerald-700 underline" data-testid={`admin-source-key-link-${k.key}`}>{t("get key")}</a>}
                  </div>))}
              </div>
            ) : <span className="text-xs text-slate-400">{t("No key needed")}</span>}</td>
          <td className="px-3 py-2"><Switch checked={s.enabled} onCheckedChange={(v) => patch(s.source_id, { enabled: v })} data-testid={`admin-source-toggle-${s.source_id}`} /></td>
          <td className="px-3 py-2"><Button size="sm" variant="ghost" onClick={() => run(s.source_id)} data-testid={`admin-source-run-${s.source_id}`}><Play className="h-3.5 w-3.5" /></Button></td></tr>))}</tbody></table></Card>
    </div>
  );
}

function ProviderRow({ p, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(p.base_url === p.default_base_url ? "" : p.base_url);
  const [busy, setBusy] = useState(false);
  const [discovered, setDiscovered] = useState(null);

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/admin/ai/providers/${p.provider}`, { api_key: key.trim(), base_url: baseUrl.trim() });
      setKey(""); setEditing(false);
      setDiscovered(null);
      toast.success(`${p.label} key saved`);
      onChanged();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await api.delete(`/admin/ai/providers/${p.provider}`);
      setDiscovered(null);
      toast.success(`${p.label} key removed`);
      onChanged();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const loadModels = async () => {
    setBusy(true);
    try {
      const { data } = await api.get(`/admin/ai/providers/${p.provider}/models`, { params: { refresh: true } });
      setDiscovered(data);
      if (data.error) toast.error(`Could not read models: ${data.error}`);
      else toast.success(`${data.models.length} models available`);
      onChanged();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="border-t py-3 first:border-t-0" data-testid={`admin-provider-${p.provider}`}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-40">
          <div className="text-sm font-semibold">{p.label}</div>
          <div className="font-mono text-[10px] text-slate-400">{p.api} · {p.env_var}</div>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs ${p.configured ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500"}`}
              data-testid={`admin-provider-status-${p.provider}`}>
          {p.configured ? `configured · ${p.source}` : "no key"}
        </span>
        {p.configured && <span className="font-mono text-xs text-slate-500">{p.key_hint}</span>}
        <div className="ms-auto flex flex-wrap gap-2">
            {p.configured && <Button size="sm" variant="ghost" onClick={loadModels} disabled={busy} data-testid={`admin-provider-models-${p.provider}`}>{t("Load models")}</Button>}
          <Button size="sm" variant="outline" onClick={() => { setEditing((v) => !v); setBaseUrl(p.base_url === p.default_base_url ? "" : p.base_url); }} disabled={busy} data-testid={`admin-provider-edit-${p.provider}`}>
            {p.configured ? "Replace key" : "Add key"}
          </Button>
            {p.source === "dashboard" && <Button size="sm" variant="ghost" className="text-rose-600" onClick={remove} disabled={busy} data-testid={`admin-provider-remove-${p.provider}`}>{t("Remove")}</Button>}
        </div>
      </div>
      {editing && (
        <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <Input type="password" autoComplete="off" placeholder={t("API key")} value={key} onChange={(e) => setKey(e.target.value)}
                 data-testid={`admin-provider-key-${p.provider}`} />
          <Input placeholder={p.default_base_url || "https://your-gateway.example/v1"} value={baseUrl}
                 onChange={(e) => setBaseUrl(e.target.value)} data-testid={`admin-provider-base-${p.provider}`} />
          <Button onClick={save} disabled={busy || (!key.trim() && !baseUrl.trim())} data-testid={`admin-provider-save-${p.provider}`}>{t("Save")}</Button>
        </div>
      )}
          {p.needs_base_url && !p.configured && <div className="mt-1 text-xs text-slate-500">{t("Needs a base URL as well as a key.")}</div>}
      {discovered && (
        <div className="mt-2 rounded bg-slate-50 p-2 text-xs" data-testid={`admin-provider-discovered-${p.provider}`}>
          <span className="font-semibold">{discovered.models.length} models</span>
          <span className="ms-2 text-slate-500">source: {discovered.source}{discovered.error ? ` · ${discovered.error}` : ""}</span>
          <div className="mt-1 max-h-32 overflow-y-auto font-mono text-[10px] text-slate-600">{discovered.models.join(", ")}</div>
        </div>
      )}
    </div>
  );
}

function AI() {
  const [c, setC] = useState(null);
  const [m, setM] = useState(null);
  const [provs, setProvs] = useState(null);
  const [img, setImg] = useState(null);
  const [catalog, setCatalog] = useState({});

  const loadProvs = () => api.get("/admin/ai/providers").then((r) => { setProvs(r.data.providers); return r.data.providers; });
  // Pull each configured provider's live model list so the dropdowns are not limited to the
  // handful of ids hardcoded in the backend catalog.
  const loadCatalog = async (list) => {
    const entries = await Promise.all(list.map(async (p) => {
      try {
        const { data } = await api.get(`/admin/ai/providers/${p.provider}/models`);
        return [p.provider, data.models || []];
      } catch { return [p.provider, []]; }
    }));
    setCatalog(Object.fromEntries(entries.filter(([, ms]) => ms.length)));
  };
  const reloadAll = () => loadProvs().then(loadCatalog);

  useEffect(() => {
    api.get("/admin/ai-costs").then((r) => setC(r.data));
    api.get("/admin/models").then((r) => setM(r.data));
    api.get("/admin/ai/image").then((r) => setImg(r.data));
    reloadAll();
  }, []); // eslint-disable-line

  const saveImage = () => api.put("/admin/ai/image", img.current)
    .then((r) => { toast.success("Image settings saved"); return api.get("/admin/ai/image").then((x) => setImg(x.data)); })
    .catch((e) => toast.error(errMsg(e)));

  if (!c || !m) return <FullLoader />;
  const all = { ...m.catalog, ...catalog };
  const opts = Object.entries(all).flatMap(([p, ms]) => ms.map((x) => [`${p}|${x}`, `${p} · ${x}`]));
  const setTier = (tier, v) => { const [provider, model] = v.split("|"); setM({ ...m, current: { ...m.current, [tier]: { provider, model } } }); };
  const save = () => api.put("/admin/models", m.current).then(() => toast.success("Models saved")).catch((e) => toast.error(errMsg(e)));

  return (
    <div className="space-y-4">
      <Card data-testid="admin-ai-providers">
        <div className="mb-1 flex items-center justify-between">
          <div>
        <div className="jp-eyebrow">{t("AI providers")}</div>
        <div className="text-xs text-slate-500">{t("Keys are encrypted at rest and never sent back to the browser.")}</div>
          </div>
          <Button size="sm" variant="ghost" onClick={reloadAll} data-testid="admin-providers-refresh">{t("Refresh")}</Button>
        </div>
        {!provs ? <div className="py-3 text-sm text-slate-400">Loading…</div> : provs.map((p) => <ProviderRow key={p.provider} p={p} onChanged={reloadAll} />)}
      </Card>
      <Card data-testid="admin-image">
        <div className="mb-1">
          <div className="jp-eyebrow">{t("Image generation")}</div>
          <div className="text-xs text-slate-500">
            Uses the same provider keys configured above. Gemini uses its native image API; OpenAI and
            custom endpoints use <span className="font-mono">/images/generations</span>.
          </div>
        </div>
        {!img ? <div className="py-3 text-sm text-slate-400">Loading…</div> : (
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <div><div className="jp-eyebrow mb-1">{t("Provider")}</div>
              <SimpleSelect testid="admin-image-provider" value={img.current.provider}
                onChange={(v) => setImg({ ...img, current: { ...img.current, provider: v } })}
                options={img.providers.map((p) => [p, p])} /></div>
            <div className="min-w-[220px] flex-1"><div className="jp-eyebrow mb-1">{t("Model")}</div>
              <Input data-testid="admin-image-model" value={img.current.model}
                onChange={(e) => setImg({ ...img, current: { ...img.current, model: e.target.value } })} /></div>
            <div className="flex items-center gap-2">
              {!img.configured && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">no key for {img.current.provider}</span>}
              <Button onClick={saveImage} className="bg-emerald-900 hover:bg-emerald-800" data-testid="admin-image-save">{t("Save image settings")}</Button>
            </div>
          </div>
        )}
      </Card>
      <Card className="grid gap-4 sm:grid-cols-3" data-testid="admin-models">
        {["scoring", "writing"].map((tier) => <div key={tier}><div className="jp-eyebrow mb-1">{tier} model</div><SimpleSelect testid={`admin-model-${tier}`} value={`${m.current[tier].provider}|${m.current[tier].model}`} onChange={(v) => setTier(tier, v)} options={opts} /></div>)}
          <div className="flex items-end"><Button onClick={save} className="w-full bg-emerald-900 hover:bg-emerald-800" data-testid="admin-models-save">{t("Save models")}</Button></div>
        <div className="font-mono text-xs text-slate-500 sm:col-span-3">
          {Object.keys(catalog).length ? `${Object.values(catalog).flat().length} models loaded live from ${Object.keys(catalog).length} provider(s) · ` : ""}
          Prompts: {Object.entries(m.prompts).map(([k, v]) => `${v.version} (${v.tier})`).join(" · ")}
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-x-auto p-0"><div className="p-4 font-heading font-semibold">{t("Cost by feature (30d)")}</div><table className="w-full text-sm"><Th cols={[t("Feature"), t("Model"), t("Calls"), t("Cached"), t("Cost $")]} />
          <tbody>{c.by_feature.map((r, i) => <tr key={i} className="border-t font-mono text-xs"><td className="px-3 py-2">{r.feature}</td><td className="px-3 py-2">{r.model}</td><td className="px-3 py-2">{r.calls}</td><td className="px-3 py-2">{r.cached}</td><td className="px-3 py-2">{r.cost}</td></tr>)}</tbody></table></Card>
        <Card className="overflow-x-auto p-0"><div className="p-4 font-heading font-semibold">{t("Cost by user (30d)")}</div><table className="w-full text-sm"><Th cols={[t("User"), t("Calls"), t("Cost $")]} />
          <tbody>{c.by_user.map((r) => <tr key={r.user_id} className="border-t font-mono text-xs"><td className="px-3 py-2">{r.email}</td><td className="px-3 py-2">{r.calls}</td><td className="px-3 py-2">{r.cost}</td></tr>)}</tbody></table></Card>
      </div>
    </div>
  );
}

function Audit() {
  const { fmtDateTime } = useI18n();
  const [q, setQ] = useState("");
  const [logs, setLogs] = useState(null);
  const load = () => api.get("/admin/audit", { params: { action: q } }).then((r) => setLogs(r.data));
  useEffect(() => { load(); }, []); // eslint-disable-line
  return (
      <Card className="p-0"><div className="flex gap-2 p-4"><Input data-testid="admin-audit-filter" placeholder={t("Filter action (login, export, deleted…)")} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} /></div>
      <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="admin-audit-table"><Th cols={["When", "Action", "User", "Actor", "Details", "IP"]} />
        <tbody>{(logs || []).map((l) => <tr key={l.log_id} className="border-t font-mono text-xs"><td className="px-3 py-2">{fmtDateTime(l.created_at)}</td><td className="px-3 py-2">{l.action}</td><td className="px-3 py-2">{l.user_email}</td><td className="px-3 py-2">{l.actor_email}</td>
          <td className="max-w-xs truncate px-3 py-2" title={JSON.stringify(l.meta)}>{JSON.stringify(l.meta)}</td><td className="px-3 py-2">{l.ip || ""}</td></tr>)}</tbody></table></div></Card>
  );
}

function Evaluation() {
  const { fmtDateTime } = useI18n();
  const [d, setD] = useState(null);
  const load = () => api.get("/admin/eval/runs").then((r) => setD(r.data));
  useEffect(() => { load(); const i = setInterval(load, 8000); return () => clearInterval(i); }, []);
  const run = () => api.post("/admin/eval/run").then(() => { toast.success("Evaluation started (~2-4 min)"); load(); });
  if (!d) return <FullLoader />;
  return (
    <div className="space-y-4" data-testid="admin-eval">
      <Card className="flex flex-wrap items-center gap-3"><div className="flex-1 text-sm text-slate-600">{t("{n} anonymised CV/job cases (EN + AR) · metrics: verdict agreement, skill recall, validator recall on seeded fake facts, Arabic agreement, cost. Grow the set in").replace("{n}", d.cases)} <code>backend/eval/cases.json</code>.</div>
        <Button onClick={run} className="bg-emerald-900 hover:bg-emerald-800" data-testid="admin-eval-run"><Play className="me-2 h-4 w-4" />{t("Run evaluation")}</Button></Card>
      {d.runs.map((r) => (
        <Card key={r.run_id} data-testid={`eval-run-${r.run_id}`}>
          <div className="flex flex-wrap items-center gap-3 text-sm"><span className="font-mono text-xs">{fmtDateTime(r.created_at)}</span><span className={`rounded px-2 py-0.5 text-xs ${r.status === "done" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{r.status}</span>
            <span className="font-mono text-xs text-slate-500">{r.models?.scoring?.model} / {r.models?.writing?.model} · {r.prompts?.review}</span></div>
          {r.metrics && <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-6">{Object.entries(r.metrics).map(([k, v]) => <div key={k}><div className="jp-eyebrow">{k.replace(/_/g, " ")}</div><div className="font-mono text-lg">{v}{/agreement|recall/.test(k) ? "%" : ""}</div></div>)}</div>}
          {r.results && <table className="mt-3 w-full text-xs"><Th cols={["Case", "Expected", "Got", "Score", "Skill recall", "Fake caught"]} />
            <tbody>{r.results.map((x) => <tr key={x.id} className="border-t font-mono"><td className="px-3 py-1.5">{x.id}</td><td className="px-3">{x.expected}</td><td className={`px-3 ${x.verdict_ok ? "text-emerald-700" : "text-rose-600"}`}>{x.verdict || x.error}</td><td className="px-3">{x.score}</td><td className="px-3">{x.skill_recall}</td><td className="px-3">{x.fake_caught ? "yes" : "no"}</td></tr>)}</tbody></table>}
        </Card>))}
    </div>
  );
}

function Integrations() {
  const [items, setItems] = useState(null);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState("");
  const load = () => api.get("/admin/integrations").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []); // eslint-disable-line

  const save = async (key, value) => {
    setSaving(key);
    try {
      await api.put("/admin/integrations/key", { key, value });
      setDraft((d) => ({ ...d, [key]: "" }));
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(""); }
  };

  if (!items) return <FullLoader />;
  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="admin-integrations">
      <Card className="md:col-span-2 text-sm text-slate-600">
        Values are encrypted at rest and take effect immediately — no restart needed. A key saved here
        overrides the same variable in the environment; clearing it falls back to the environment.
        Stored values are never sent back to this page, only whether each one is set.
      </Card>
      {items.map((it) => (
        <Card key={it.name} data-testid={`integration-${it.keys[0].key}`}>
          <div className="flex items-center justify-between"><div className="font-heading font-semibold">{it.name}</div>
            <span className={`rounded-full px-2 py-0.5 text-xs ${it.configured ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{it.configured ? "configured" : "not configured"}</span></div>
          <div className="mt-2 space-y-2">
            {it.keys.map((k) => (
              <div key={k.key}>
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${k.set ? "bg-emerald-50 text-emerald-800" : "bg-slate-100 text-slate-500"}`}>{k.set ? "✓" : "○"} {k.key}</span>
                  <div className="flex-1" />
                  <Input data-testid={`integration-input-${k.key}`} type="password" autoComplete="new-password"
                    placeholder={k.set ? "•••••••• (set — type to replace)" : "not set"}
                    value={draft[k.key] || ""}
                    onChange={(e) => setDraft((d) => ({ ...d, [k.key]: e.target.value }))} className="max-w-[220px]" />
                  <Button size="sm" variant="outline" data-testid={`integration-save-${k.key}`}
                    disabled={saving === k.key || !(draft[k.key] || "").trim()}
                    onClick={() => save(k.key, draft[k.key])}>{t("Save")}</Button>
                  {k.set && <Button size="sm" variant="ghost" data-testid={`integration-clear-${k.key}`}
                    disabled={saving === k.key} onClick={() => save(k.key, "")}>{t("Clear")}</Button>}
                </div>
              </div>))}
          </div>
          <p className="mt-2 text-xs text-slate-500">{it.help}</p>
          {it.url && <div className="mt-2 break-all rounded bg-slate-50 p-2 font-mono text-[11px]">{it.url}</div>}
        </Card>))}
    </div>
  );
}

export default function Admin() {
  const TABS = [["overview", "Overview", Overview], ["users", "Users", Users], ["plans", "Plans", Plans], ["sources", "Source health", Sources], ["ai", "AI cost & models", AI], ["eval", "Evaluation", Evaluation], ["integrations", "Integrations", Integrations], ["audit", "Audit log", Audit]];
  return (
    <div dir="ltr">
      <PageHeader eyebrow={t("Super admin")} title={t("Admin panel")} />
      <Tabs defaultValue="overview"><TabsList className="flex-wrap bg-white">{TABS.map(([k, l]) => <TabsTrigger key={k} value={k} data-testid={`admin-tab-${k}`}>{l}</TabsTrigger>)}</TabsList>
        {TABS.map(([k, , C]) => <TabsContent key={k} value={k} className="mt-4"><C /></TabsContent>)}</Tabs>
    </div>
  );
}
