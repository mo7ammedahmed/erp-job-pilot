import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Trash2, Upload, Download, Mail, Ghost, ExternalLink } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, errMsg, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { STATUSES, STATUS_LABEL } from "@/lib/constants";
import { FullLoader, Spinner } from "@/components/common";
import { SimpleSelect, Field } from "@/pages/Onboarding";

const toLocal = (iso) => (iso ? new Date(new Date(iso).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
const fromLocal = (v) => (v ? new Date(v).toISOString() : "");

function EmailTab({ a, reload }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const [st, setSt] = useState(null);
  const approved = (a.tailored_versions || []).filter((x) => x.status === "approved");
  const [f, setF] = useState({ to: a.contacts?.find((c) => c.email)?.email || "", subject: `${t("Application")}: ${a.title}`,
    body: `${t("Dear Hiring Team,")}\n\n${t("Please find attached my CV for the {role} role at {company}.", { role: a.title, company: a.company })}\n\n${t("Kind regards,")}\n${user?.name || ""}`,
    tailored_id: approved[0]?.tailored_id || "", attach: "pdf" });
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState("");
  useEffect(() => { api.get("/gmail/status").then((r) => setSt(r.data)); }, []);
  const send = async (mode) => {
    setBusy(mode);
    try {
      await api.post("/gmail/compose", { ...f, application_id: a.application_id, tailored_id: f.tailored_id || null, mode });
      toast.success(mode === "send" ? t("Email sent from your Gmail") : t("Draft saved in your Gmail"));
      if (mode === "send" && ["saved", "preparing"].includes(a.status)) await api.post(`/applications/${a.application_id}/move`, { status: "applied" });
      reload();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); setConfirm(false); }
  };
  if (!st) return <Spinner />;
  if (!st.connected) return <div className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600" data-testid="gmail-not-connected">{!st.configured ? t("Gmail isn't configured on this workspace yet.") : !st.plan_allows ? t("Gmail sending is available on Pro and Premium.") : t("Connect Gmail in Settings to send from your own account.")} <Link to="/app/settings" className="text-emerald-800 underline">{t("Settings")}</Link></div>;
  return (
    <div className="space-y-3">
      <Input data-testid="email-to" placeholder={t("To")} value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
      <Input data-testid="email-subject" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />
      <Textarea data-testid="email-body" rows={8} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} />
      <SimpleSelect testid="email-attach" value={f.tailored_id || "none"} onChange={(v) => setF({ ...f, tailored_id: v === "none" ? "" : v })}
        options={[["none", t("No attachment")], ...approved.map((x) => [x.tailored_id, `${t("Approved CV")} (${x.lang.toUpperCase()})`])]} />
      <div className="flex gap-2"><Button variant="outline" onClick={() => send("draft")} disabled={!!busy} data-testid="email-draft">{busy === "draft" && <Spinner className="me-2" />}{t("Save as Gmail draft")}</Button>
        <Button onClick={() => setConfirm(true)} disabled={!!busy || !f.to} className="bg-emerald-900 hover:bg-emerald-800" data-testid="email-send"><Mail className="me-2 h-4 w-4" />{t("Send")}</Button></div>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent className="bg-white"><AlertDialogHeader><AlertDialogTitle>{t("Send this email now?")}</AlertDialogTitle>
          <AlertDialogDescription>{t("It will be sent from {email} to {to}.", { email: st.email || "Gmail", to: f.to })}</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>{t("Cancel")}</AlertDialogCancel><AlertDialogAction onClick={() => send("send")} data-testid="email-send-confirm">{t("Send")}</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const asText = (v) => (v == null ? "" : typeof v === "string" ? v : Array.isArray(v) ? v.map(asText).join("\n") : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k}: ${asText(x)}`).join("\n") : String(v));

function PrepTab({ a, reload }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const gen = async () => {
    setBusy(true);
    try { await api.post(`/applications/${a.application_id}/prep`); await reload(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const p = a.prep;
  return (
    <div className="space-y-4" data-testid="prep-tab">
      <Button size="sm" onClick={gen} disabled={busy} className="bg-emerald-900 hover:bg-emerald-800" data-testid="prep-generate">{busy && <Spinner className="me-2" />}{p ? t("Regenerate prep pack") : t("Generate interview-prep pack")}</Button>
      {!p && <p className="text-xs text-slate-500">{t("Likely questions with answer outlines drawn only from your real CV.")}</p>}
      {p && <>
        <ol className="space-y-3">{(p.questions || []).map((q, i) => (
          <li key={i} className="rounded-lg border p-3 text-sm"><div className="font-semibold">{i + 1}. {asText(q.q)}</div><div className="mt-1 text-xs text-slate-500">{asText(q.why)}</div><div className="mt-2 whitespace-pre-wrap text-slate-700">{asText(q.answer_outline)}</div></li>))}</ol>
        {[["Gaps to prepare", p.gaps_to_prepare], ["Questions to ask them", p.questions_to_ask], ["Research", p.research]].map(([h, list]) => list?.length > 0 && (
          <div key={h}><div className="jp-eyebrow mb-1">{t(h)}</div><ul className="list-disc space-y-1 ps-5 text-sm">{list.map((x, i) => <li key={i}>{asText(x)}</li>)}</ul></div>))}
        <p className="font-mono text-[10px] text-slate-400">{p.model} · {p.prompt_version}</p></>}
    </div>
  );
}

export default function ApplicationDrawer({ id, onClose, onChanged }) {
  const { t, fmtDateTime } = useI18n();
  const [a, setA] = useState(null);
  const [note, setNote] = useState("");
  const [ct, setCt] = useState({ name: "", role: "", email: "", phone: "" });
  const [dates, setDates] = useState({});
  const fileRef = useRef();
  const load = async () => {
    const { data } = await api.get(`/applications/${id}`);
    setA(data);
    setDates({ interview_at: toLocal(data.interview_at), followup_at: toLocal(data.followup_at), deadline_at: toLocal(data.deadline_at), salary: data.salary || "" });
  };
  useEffect(() => { load(); }, [id]); // eslint-disable-line
  const call = async (fn, msg) => { try { await fn(); if (msg) toast.success(msg); await load(); onChanged(); } catch (e) { toast.error(errMsg(e)); } };
  const saveDates = () => call(() => api.patch(`/applications/${id}`, { salary: dates.salary, interview_at: fromLocal(dates.interview_at), followup_at: fromLocal(dates.followup_at), deadline_at: fromLocal(dates.deadline_at) }), t("Saved"));
  const upload = (file) => { const fd = new FormData(); fd.append("file", file); call(() => api.post(`/applications/${id}/documents`, fd), t("Uploaded")); };
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto bg-white sm:max-w-xl" data-testid="application-drawer">
        {!a ? <FullLoader /> : <>
          <SheetHeader><SheetTitle className="text-start font-heading text-xl">{a.title}</SheetTitle><div className="text-start text-sm text-slate-500">{a.company} · <span className="capitalize">{a.source}</span></div></SheetHeader>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <div className="w-44"><SimpleSelect testid="drawer-status" value={a.status} onChange={(v) => call(() => api.post(`/applications/${id}/move`, { status: v }))} options={STATUSES.map((s) => [s, t(STATUS_LABEL[s])])} /></div>
            {a.job_id && <Link to={`/app/jobs/${a.job_id}`}><Button variant="outline" size="sm">{t("Job & AI review")}</Button></Link>}
            {a.url && <a href={a.url} target="_blank" rel="noreferrer"><Button variant="ghost" size="sm"><ExternalLink className="h-4 w-4" /></Button></a>}
            <Button variant="ghost" size="sm" className="ms-auto text-rose-600" data-testid="drawer-delete" onClick={() => call(() => api.delete(`/applications/${id}`)).then(onClose)}><Trash2 className="h-4 w-4" /></Button>
          </div>
          {a.ghost_suggested && <div className="mt-3 flex items-center gap-2 rounded-lg bg-slate-100 p-3 text-sm"><Ghost className="h-4 w-4" />{t("No reply for a while. Mark as Ghosted?")}
            <Button size="sm" variant="outline" className="ms-auto" onClick={() => call(() => api.post(`/applications/${id}/move`, { status: "ghosted" }))} data-testid="drawer-mark-ghosted">{t("Mark ghosted")}</Button></div>}
          <Tabs defaultValue="overview" className="mt-5">
            <TabsList className="flex w-full justify-start overflow-x-auto bg-slate-100">{["overview", "notes", "contacts", "documents", "timeline", "prep", "email"].map((k) => <TabsTrigger key={k} value={k} data-testid={`drawer-tab-${k}`} className="shrink-0 px-2.5">{t(k === "prep" ? "Prep" : k[0].toUpperCase() + k.slice(1))}</TabsTrigger>)}</TabsList>
            <TabsContent value="overview" className="space-y-3 pt-3">
              <Field label={t("Interview date")}><Input type="datetime-local" data-testid="drawer-interview-at" value={dates.interview_at} onChange={(e) => setDates({ ...dates, interview_at: e.target.value })} /></Field>
              <Field label={t("Follow-up date")} hint={t("Leave empty to use your default follow-up rule.")}><Input type="datetime-local" data-testid="drawer-followup-at" value={dates.followup_at} onChange={(e) => setDates({ ...dates, followup_at: e.target.value })} /></Field>
              <Field label={t("Application deadline")}><Input type="datetime-local" data-testid="drawer-deadline-at" value={dates.deadline_at} onChange={(e) => setDates({ ...dates, deadline_at: e.target.value })} /></Field>
              <Field label={t("Salary / offer notes")}><Input data-testid="drawer-salary" value={dates.salary} onChange={(e) => setDates({ ...dates, salary: e.target.value })} /></Field>
              <Button onClick={saveDates} className="bg-emerald-900 hover:bg-emerald-800" data-testid="drawer-save">{t("Save")}</Button>
              {a.reminders?.length > 0 && <div className="border-t pt-3"><div className="jp-eyebrow mb-2">{t("Reminders")}</div>{a.reminders.map((r) => <div key={r.reminder_id} className="flex justify-between py-1 text-sm"><span>{r.title}</span><span className="font-mono text-xs text-slate-500">{fmtDateTime(r.due_at)} · {t(r.status)}</span></div>)}</div>}
            </TabsContent>
            <TabsContent value="notes" className="space-y-3 pt-3">
              <Textarea data-testid="note-input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("Write a note…")} />
              <Button size="sm" disabled={!note} data-testid="note-add" onClick={() => call(() => api.post(`/applications/${id}/notes`, { text: note })).then(() => setNote(""))}>{t("Add note")}</Button>
              {a.notes.map((n) => <div key={n.note_id} className="rounded-lg bg-slate-50 p-3 text-sm"><div className="whitespace-pre-wrap">{n.text}</div><div className="mt-1 flex justify-between text-xs text-slate-400">{fmtDateTime(n.created_at)}<button onClick={() => call(() => api.delete(`/applications/${id}/notes/${n.note_id}`))}><Trash2 className="h-3 w-3" /></button></div></div>)}
            </TabsContent>
            <TabsContent value="contacts" className="space-y-3 pt-3">
              <div className="grid grid-cols-2 gap-2">{["name", "role", "email", "phone"].map((k) => <Input key={k} data-testid={`contact-${k}`} placeholder={t(k[0].toUpperCase() + k.slice(1))} value={ct[k]} onChange={(e) => setCt({ ...ct, [k]: e.target.value })} />)}</div>
              <Button size="sm" disabled={!ct.name} data-testid="contact-add" onClick={() => call(() => api.post(`/applications/${id}/contacts`, ct)).then(() => setCt({ name: "", role: "", email: "", phone: "" }))}>{t("Add contact")}</Button>
              {a.contacts.map((c) => <div key={c.contact_id} className="flex items-center justify-between rounded-lg border p-3 text-sm"><div><div className="font-semibold">{c.name} <span className="font-normal text-slate-500">{c.role}</span></div><div className="text-xs text-slate-500">{c.email} {c.phone}</div></div>
                <button onClick={() => call(() => api.delete(`/applications/${id}/contacts/${c.contact_id}`))}><Trash2 className="h-3.5 w-3.5 text-slate-400" /></button></div>)}
            </TabsContent>
            <TabsContent value="documents" className="space-y-2 pt-3">
              <input ref={fileRef} type="file" className="hidden" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} data-testid="doc-file-input" />
              <Button size="sm" variant="outline" onClick={() => fileRef.current.click()} data-testid="doc-upload"><Upload className="me-2 h-3.5 w-3.5" />{t("Upload file")}</Button>
              {a.documents.map((d, i) => <div key={i} className="flex items-center justify-between rounded-lg border p-3 text-sm"><span>{d.filename}</span>
                {d.tailored_id ? <Link to={`/app/tailor/${d.tailored_id}`} className="text-xs text-emerald-800 underline">{t("Open")}</Link> :
                  <button onClick={() => download(`/files/${d.file_id}`, d.filename)}><Download className="h-3.5 w-3.5 text-slate-500" /></button>}</div>)}
            </TabsContent>
            <TabsContent value="timeline" className="pt-3"><ol className="relative space-y-3 border-s border-slate-200 ps-4" data-testid="drawer-timeline">{[...a.timeline].reverse().map((e) => (
              <li key={e.event_id} className="text-sm"><span className="absolute -start-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white bg-emerald-700" /><div>{e.text}</div><div className="font-mono text-xs text-slate-400">{fmtDateTime(e.at)}</div></li>))}</ol></TabsContent>
            <TabsContent value="prep" className="pt-3"><PrepTab a={a} reload={load} /></TabsContent>
            <TabsContent value="email" className="pt-3"><EmailTab a={a} reload={load} /></TabsContent>
          </Tabs></>}
      </SheetContent>
    </Sheet>
  );
}
