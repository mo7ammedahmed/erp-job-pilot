import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Mail, MessageCircle, Download, Trash2, ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api, API, errMsg, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { COUNTRIES, TIMEZONES } from "@/lib/constants";
import { PageHeader, Card, Spinner } from "@/components/common";
import { SimpleSelect, Field } from "@/pages/Onboarding";

function Profile() {
  const { t, lang, setLang } = useI18n();
  const { user, setUser } = useAuth();
  const keys = ["name", "lang", "country", "city", "timezone", "quiet_start", "quiet_end", "weekly_goal", "followup_days", "ghost_days"];
  const [f, setF] = useState(Object.fromEntries(keys.map((k) => [k, user[k]])));
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const save = async () => {
    try {
      const { data } = await api.patch("/me", { ...f, weekly_goal: +f.weekly_goal, followup_days: +f.followup_days, ghost_days: +f.ghost_days });
      setUser(data); setLang(data.lang); toast.success(t("Saved"));
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card className="grid gap-4 sm:grid-cols-2">
      <Field label={t("Full name")}><Input data-testid="settings-name" value={f.name} onChange={(e) => set("name")(e.target.value)} /></Field>
      <Field label={t("Language")}><SimpleSelect testid="settings-lang" value={f.lang} onChange={set("lang")} options={[["en", "English"], ["ar", "العربية"]]} /></Field>
      <Field label={t("Country")}><SimpleSelect testid="settings-country" value={f.country} onChange={set("country")} options={COUNTRIES.map((x) => [x[0], lang === "ar" ? x[2] : x[1]])} /></Field>
      <Field label={t("City")}><Input value={f.city} onChange={(e) => set("city")(e.target.value)} /></Field>
      <Field label={t("Timezone")}><SimpleSelect testid="settings-timezone" value={f.timezone} onChange={set("timezone")} options={TIMEZONES.map((z) => [z, z])} /></Field>
      <div className="grid grid-cols-2 gap-2"><Field label={t("Quiet from")}><Input type="time" data-testid="settings-quiet-start" value={f.quiet_start} onChange={(e) => set("quiet_start")(e.target.value)} /></Field>
        <Field label={t("Quiet until")}><Input type="time" data-testid="settings-quiet-end" value={f.quiet_end} onChange={(e) => set("quiet_end")(e.target.value)} /></Field></div>
      <Field label={t("Weekly application goal")}><Input type="number" data-testid="settings-weekly-goal" value={f.weekly_goal} onChange={(e) => set("weekly_goal")(e.target.value)} /></Field>
      <Field label={t("Follow up after (days)")}><Input type="number" data-testid="settings-followup-days" value={f.followup_days} onChange={(e) => set("followup_days")(e.target.value)} /></Field>
      <Field label={t("Suggest “Ghosted” after (days)")}><Input type="number" data-testid="settings-ghost-days" value={f.ghost_days} onChange={(e) => set("ghost_days")(e.target.value)} /></Field>
      <div className="sm:col-span-2"><Button onClick={save} className="bg-emerald-900 hover:bg-emerald-800" data-testid="settings-save">{t("Save changes")}</Button></div>
    </Card>
  );
}

function Avatar() {
  const { t } = useI18n();
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [src, setSrc] = useState(null);
  const [style, setStyle] = useState("minimal flat illustration");
  const loadImg = () => user?.avatar_file_id && api.get("/me/avatar", { responseType: "blob" }).then((r) => setSrc(URL.createObjectURL(r.data))).catch(() => {});
  useEffect(() => { loadImg(); }, [user?.avatar_file_id]); // eslint-disable-line
  const gen = async () => {
    setBusy(true);
    try { await api.post("/me/avatar", { style }); await refresh(); toast.success(t("New avatar ready")); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Card className="flex flex-col gap-4 sm:flex-row sm:items-center" data-testid="avatar-card">
      <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-emerald-50">{src ? <img src={src} alt={t("Profile photo")} className="h-full w-full object-cover" data-testid="avatar-image" /> : <ImagePlus className="h-6 w-6 text-emerald-800" />}</div>
      <div className="flex-1 space-y-2"><div className="font-heading font-semibold">{t("AI profile avatar")}</div>
        <p className="text-xs text-slate-500">{t("Generate a professional, privacy-friendly avatar (no photo needed).")}</p>
        <div className="flex gap-2"><Input data-testid="avatar-style" value={style} onChange={(e) => setStyle(e.target.value)} />
          <Button onClick={gen} disabled={busy} data-testid="avatar-generate" className="bg-emerald-900 hover:bg-emerald-800">{busy ? <Spinner /> : t("Generate")}</Button></div></div>
    </Card>
  );
}

function WhatsApp() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const [st, setSt] = useState(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [consent, setConsent] = useState(false);
  const load = () => api.get("/whatsapp/status").then((r) => setSt(r.data));
  useEffect(() => { load(); }, []);
  const act = (p, msg) => p.then(() => { if (msg) toast.success(msg); load(); refresh(); }).catch((e) => toast.error(errMsg(e)));
  const status = !st ? "" : st.opted_in ? `${t("Connected")}: +${st.phone}` : !st.configured ? t("Not connected — WhatsApp Business credentials are not configured yet") : !st.plan_allows ? t("Available on Premium") : t("Not connected");
  return (
    <Card className="space-y-3" data-testid="whatsapp-card">
      <div className="flex flex-wrap items-center gap-4"><MessageCircle className="h-6 w-6 text-emerald-600" /><div className="flex-1"><div className="font-heading font-semibold">WhatsApp</div>
        <p className="text-xs text-slate-500">{t("Official WhatsApp Business reminders with opt-in and one-tap “done / snooze” replies.")}</p>
        <p className="mt-1 text-xs font-medium" data-testid="whatsapp-status">{status}</p></div>
        {st?.opted_in && <Button variant="outline" onClick={() => act(api.post("/whatsapp/opt-out"))} data-testid="whatsapp-optout">{t("Disconnect")}</Button>}</div>
      {st && st.configured && st.plan_allows && !st.opted_in && <div className="space-y-2 border-t pt-3">
        <div className="flex gap-2"><Input data-testid="whatsapp-phone" placeholder="+9665XXXXXXXX" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <Button variant="outline" onClick={() => act(api.post("/whatsapp/start", { phone }).then(() => setSent(true)))} data-testid="whatsapp-send-code">{t("Send code")}</Button></div>
        {sent && <><Input data-testid="whatsapp-code" placeholder={t("6-digit code")} value={code} onChange={(e) => setCode(e.target.value)} />
          <label className="flex items-start gap-2 text-xs"><Switch checked={consent} onCheckedChange={setConsent} data-testid="whatsapp-consent" />{t("I agree to receive JobPilot reminders on WhatsApp. Reply STOP anytime to opt out.")}</label>
          <Button disabled={!consent || code.length < 6} onClick={() => act(api.post("/whatsapp/verify", { code, consent }), t("WhatsApp connected"))} className="bg-emerald-900 hover:bg-emerald-800" data-testid="whatsapp-verify">{t("Verify")}</Button></>}
      </div>}
    </Card>
  );
}

function SaveJobSnippet() {
  const { t } = useI18n();
  const code = `javascript:(()=>{const s=(getSelection().toString()||document.body.innerText).slice(0,6000);window.open('${window.location.origin}/app/jobs?add_url='+encodeURIComponent(location.href)+'&add_text='+encodeURIComponent(s))})()`;
  const copy = () => navigator.clipboard.writeText(code).then(() => toast.success(t("Copied")));
  return (
    <Card className="space-y-2" data-testid="save-job-card"><div className="font-heading font-semibold">{t("Save jobs from any site")}</div>
      <p className="text-xs text-slate-500">{t("Create a browser bookmark and paste this as its URL. On any job page, select the description (or nothing) and click the bookmark — only what you see is sent to JobPilot.")}</p>
      <div className="flex gap-2"><Input readOnly value={code} className="font-mono text-xs" /><Button variant="outline" onClick={copy} data-testid="save-job-copy">{t("Copy")}</Button></div></Card>
  );
}

function Integrations() {
  const { t } = useI18n();
  const [st, setSt] = useState(null);
  const load = () => api.get("/gmail/status").then((r) => setSt(r.data));
  useEffect(() => { load(); }, []);
  const connect = async () => { try { window.location.href = (await api.get("/gmail/connect")).data.url; } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-4" data-testid="gmail-card">
        <Mail className="h-6 w-6 text-rose-600" /><div className="flex-1"><div className="font-heading font-semibold">Gmail</div>
          <p className="text-xs text-slate-500">{t("Create drafts and send applications from your own account. Every send needs your click.")}</p>
          {st && <p className="mt-1 text-xs font-medium" data-testid="gmail-status">{st.connected ? `${t("Connected")}: ${st.email}` : !st.configured ? t("Not connected — Google OAuth credentials are not configured yet") : !st.plan_allows ? t("Available on Pro and Premium") : t("Not connected")}</p>}</div>
        {st?.connected ? <Button variant="outline" onClick={() => api.post("/gmail/disconnect").then(load)} data-testid="gmail-disconnect">{t("Disconnect")}</Button> :
          <Button onClick={connect} disabled={!st?.configured} data-testid="gmail-connect" className="bg-emerald-900 hover:bg-emerald-800">{t("Connect Gmail")}</Button>}
      </Card>
      <WhatsApp />
      <SaveJobSnippet />
    </div>
  );
}

function Privacy() {
  const { t, fmtDateTime } = useI18n();
  const { logout } = useAuth();
  const [c, setC] = useState(null);
  const [del, setDel] = useState(false);
  const [confirm, setConfirm] = useState("");
  const load = () => api.get("/privacy/consents").then((r) => setC(r.data));
  useEffect(() => { load(); }, []);
  const toggle = (type, granted) => api.post("/privacy/consents", { type, granted }).then(load).catch((e) => toast.error(errMsg(e)));
  const remove = async () => {
    try { await api.delete("/privacy/account", { data: { confirm } }); await logout(); window.location.href = "/"; } catch (e) { toast.error(errMsg(e)); }
  };
  const LABELS = { ai_processing: "AI processing of my CV", email_messaging: "Email reminders & job alerts", whatsapp_messaging: "WhatsApp reminders (Phase 2)", inbox_scanning: "Gmail inbox scanning (Phase 2)" };
  return (
    <div className="space-y-4">
      <Card data-testid="consents-card"><div className="mb-3 font-heading font-semibold">{t("Consents")}</div>
        {c && Object.entries(LABELS).map(([k, label]) => (
          <label key={k} className="flex items-center justify-between border-t py-3 text-sm"><span>{t(label)}</span><Switch data-testid={`consent-toggle-${k}`} checked={!!c.current[k]} onCheckedChange={(v) => toggle(k, v)} /></label>))}
        {c?.history?.length > 0 && <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer">{t("Consent history")}</summary>{c.history.map((h, i) => <div key={i} className="font-mono">{fmtDateTime(h.created_at)} · {h.type} · {h.granted ? "✓" : "✗"}</div>)}</details>}
      </Card>
      <Card className="flex flex-wrap items-center gap-3"><div className="flex-1"><div className="font-heading font-semibold">{t("Export my data")}</div><p className="text-xs text-slate-500">{t("Everything you own as JSON, including your files.")}</p></div>
        <Button variant="outline" onClick={() => download("/privacy/export", "jobpilot-export.json")} data-testid="privacy-export"><Download className="me-2 h-4 w-4" />{t("Export")}</Button></Card>
      <Card className="flex flex-wrap items-center gap-3 border-rose-200"><div className="flex-1"><div className="font-heading font-semibold text-rose-700">{t("Delete my account")}</div><p className="text-xs text-slate-500">{t("Permanently deletes your CVs, files, applications and connected accounts.")}</p></div>
        <Button variant="outline" className="border-rose-300 text-rose-700" onClick={() => setDel(true)} data-testid="privacy-delete"><Trash2 className="me-2 h-4 w-4" />{t("Delete")}</Button></Card>
      <Dialog open={del} onOpenChange={setDel}><DialogContent className="bg-white"><DialogHeader><DialogTitle>{t("Delete account permanently?")}</DialogTitle>
        <DialogDescription>{t("Type DELETE to confirm. This cannot be undone.")}</DialogDescription></DialogHeader>
        <Input data-testid="delete-confirm-input" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <Button disabled={confirm !== "DELETE"} onClick={remove} className="bg-rose-600 hover:bg-rose-700" data-testid="delete-confirm-button">{t("Delete forever")}</Button></DialogContent></Dialog>
    </div>
  );
}

function ApplyProfile() {
  const { t } = useI18n();
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/apply/profile").then(({ data }) => setF(data)).catch((e) => toast.error(errMsg(e)));
  }, []);
  if (!f) return null;
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.put("/apply/profile", f);
      setF(data); toast.success(t("Saved"));
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Card className="space-y-4" data-testid="apply-profile-card">
      <div>
        <div className="font-heading font-semibold" data-testid="apply-profile-title">{t("Apply profile")}</div>
        <p className="text-xs text-slate-500">
          {t("These details are filled into employer application forms when you use auto-apply.")}
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("First name")}><Input data-testid="apply-first-name" value={f.first_name || ""} onChange={(e) => set("first_name")(e.target.value)} /></Field>
        <Field label={t("Last name")}><Input data-testid="apply-last-name" value={f.last_name || ""} onChange={(e) => set("last_name")(e.target.value)} /></Field>
        <Field label={t("Email")}><Input data-testid="apply-email" value={f.email || ""} onChange={(e) => set("email")(e.target.value)} /></Field>
        <Field label={t("Phone")}><Input data-testid="apply-phone" value={f.phone || ""} onChange={(e) => set("phone")(e.target.value)} /></Field>
        <Field label="LinkedIn"><Input data-testid="apply-linkedin" value={f.linkedin || ""} onChange={(e) => set("linkedin")(e.target.value)} /></Field>
        <Field label={t("Location")}><Input value={f.location || ""} onChange={(e) => set("location")(e.target.value)} /></Field>
      </div>
      <Field label={t("Cover letter")}>
        <textarea
          data-testid="apply-cover-letter" rows={4} value={f.cover_letter || ""}
          onChange={(e) => set("cover_letter")(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-700 focus:outline-none"
        />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox" data-testid="apply-attach-cv" checked={f.attach_cv !== false}
          onChange={(e) => set("attach_cv")(e.target.checked)}
        />
        {t("Attach my master CV to applications")}
      </label>
      <Button onClick={save} disabled={busy} data-testid="apply-profile-save">
        {busy ? <Spinner className="me-2" /> : null}{t("Save")}
      </Button>
    </Card>
  );
}

export default function SettingsPage() {
  const { t } = useI18n();
  const [sp] = useSearchParams();
  useEffect(() => {
    if (sp.get("gmail") === "connected") toast.success(t("Gmail connected"));
    if (sp.get("gmail") === "error") toast.error(t("Gmail connection failed"));
  }, []); // eslint-disable-line
  return (
    <div>
      <PageHeader eyebrow={t("Settings")} title={t("Settings")} />
      <Tabs defaultValue={sp.get("gmail") ? "integrations" : "profile"}>
        <TabsList className="bg-white">{[["profile", "Profile"], ["integrations", "Integrations"], ["privacy", "Privacy & data"]].map(([k, l]) => <TabsTrigger key={k} value={k} data-testid={`settings-tab-${k}`}>{t(l)}</TabsTrigger>)}</TabsList>
        <TabsContent value="profile" className="mt-4 space-y-4"><Profile /><Avatar /><ApplyProfile /></TabsContent>
        <TabsContent value="integrations" className="mt-4"><Integrations /></TabsContent>
        <TabsContent value="privacy" className="mt-4"><Privacy /></TabsContent>
      </Tabs>
      <span className="hidden">{API}</span>
    </div>
  );
}
