import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { diffWords } from "diff";
import { ShieldCheck, ShieldAlert, CheckCircle2, Trash2, RefreshCw, Download, ArrowLeft, Save, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errMsg, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Card, FullLoader, Spinner } from "@/components/common";
import CVEditor, { cvToText, cleanCV } from "@/components/CVEditor";

function Diff({ master, tailored }) {
  const { t } = useI18n();
  const parts = useMemo(() => diffWords(master, tailored), [master, tailored]);
  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="tailor-diff">
      <div className="rounded-lg border border-slate-200 bg-white p-4"><div className="jp-eyebrow mb-3">{t("Master CV")}</div>
        <div className="whitespace-pre-wrap text-sm leading-relaxed">{parts.filter((p) => !p.added).map((p, i) => <span key={i} className={p.removed ? "jp-diff-del" : ""}>{p.value}</span>)}</div></div>
      <div className="rounded-lg border border-emerald-200 bg-white p-4"><div className="jp-eyebrow mb-3 text-emerald-800">{t("Tailored version")}</div>
        <div className="whitespace-pre-wrap text-sm leading-relaxed">{parts.filter((p) => !p.removed).map((p, i) => <span key={i} className={p.added ? "jp-diff-add" : ""}>{p.value}</span>)}</div></div>
    </div>
  );
}

function Flags({ tl, onAction, locked }) {
  const { t } = useI18n();
  const open = tl.flags.filter((f) => f.status === "open");
  return (
    <Card data-testid="validation-panel">
      <div className="mb-3 flex items-center gap-2">
        {open.length ? <ShieldAlert className="h-5 w-5 text-rose-600" /> : <ShieldCheck className="h-5 w-5 text-emerald-700" />}
        <div className="font-heading font-semibold">{t("Validation check")}</div>
        <span data-testid="validation-open-count" className={`ms-auto rounded-full px-2 py-0.5 font-mono text-xs ${open.length ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-800"}`}>{open.length} {t("open")}</span>
      </div>
      <p className="mb-3 text-xs text-slate-500">{t("Anything not found in your master CV is flagged. Remove it, or confirm it is true before approving.")}</p>
      {tl.flags.length === 0 && <p className="text-sm text-emerald-800">{t("No unsupported claims found.")}</p>}
      <ul className="space-y-2">{tl.flags.map((f) => (
        <li key={f.flag_id} data-testid={`flag-${f.flag_id}`} className={`rounded-lg border p-3 text-sm ${f.status === "open" ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-slate-50 opacity-70"}`}>
          <div className="flex items-center gap-2"><span className="rounded bg-white px-1.5 py-0.5 font-mono text-[10px] uppercase text-slate-600">{t(f.type)}</span>
            <span className="font-mono text-[10px] text-slate-400">{f.path}</span><span className="ms-auto text-[10px] uppercase text-slate-400">{t(f.status)}</span></div>
          <div className="mt-1.5 font-semibold text-slate-900">“{f.value}”</div>
          <div className="text-xs text-slate-600">{f.reason}</div>
          {!locked && f.status === "open" && <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" className="h-7 border-rose-300 text-rose-700" onClick={() => onAction(f.flag_id, "remove")} data-testid={`flag-remove-${f.flag_id}`}><Trash2 className="me-1 h-3 w-3" />{t("Remove")}</Button>
            <Button size="sm" variant="outline" className="h-7" onClick={() => onAction(f.flag_id, "confirm")} data-testid={`flag-confirm-${f.flag_id}`}><CheckCircle2 className="me-1 h-3 w-3" />{t("It's true")}</Button></div>}
          {!locked && f.status !== "open" && <button className="mt-1 text-xs text-slate-500 underline" onClick={() => onAction(f.flag_id, "reopen")}>{t("Undo")}</button>}
        </li>))}</ul>
    </Card>
  );
}

export default function Tailor() {
  const { id } = useParams();
  const { t } = useI18n();
  const [tl, setTl] = useState(null);
  const [cv, setCv] = useState(null);
  const [cover, setCover] = useState("");
  const [busy, setBusy] = useState("");
  const apply = (data) => { setTl(data); setCv(data.cv); setCover(data.cover_letter); };
  useEffect(() => { api.get(`/tailor/${id}`).then((r) => apply(r.data)); }, [id]);
  const run = async (name, fn) => { setBusy(name); try { await fn(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); } };
  if (!tl) return <FullLoader />;
  const locked = tl.status === "approved";
  const open = tl.flags.filter((f) => f.status === "open").length;
  const saveEdits = () => run("save", async () => apply((await api.patch(`/tailor/${id}`, { cv: cleanCV(cv), cover_letter: cover })).data));
  const flag = (fid, action) => run("flag", async () => apply((await api.post(`/tailor/${id}/flags/${fid}`, { action })).data));
  const revalidate = () => run("reval", async () => { await api.patch(`/tailor/${id}`, { cv: cleanCV(cv), cover_letter: cover }); apply((await api.post(`/tailor/${id}/revalidate`)).data); });
  const approve = () => run("approve", async () => { await api.post(`/tailor/${id}/approve`); toast.success(t("Approved and linked to your application")); apply((await api.get(`/tailor/${id}`)).data); });
  const exp = (fmt, doc) => download(`/tailor/${id}/export?fmt=${fmt}&doc=${doc}`, `${doc === "cover" ? "CoverLetter" : "CV"}_${tl.company}.${fmt}`).catch((e) => toast.error(errMsg(e)));
  return (
    <div dir={tl.lang === "ar" ? "rtl" : undefined}>
      <Link to={`/app/jobs/${tl.job_id}`} className="mb-4 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft className="h-4 w-4 rtl:rotate-180" />{t("Back to job")}</Link>
      <div className="sticky top-14 z-10 -mx-4 mb-6 flex flex-wrap items-center gap-3 border-b border-slate-200 bg-[#F8FAFC]/90 px-4 py-3 backdrop-blur-xl sm:-mx-6 sm:px-6">
        <div className="min-w-0 flex-1"><div className="jp-eyebrow">{t("Tailor studio")} · {tl.lang.toUpperCase()} · {t("from master")} v{tl.cv_version}</div>
          <div className="truncate font-heading text-lg font-bold">{tl.job_title} · {tl.company}</div></div>
        <span data-testid="tailor-status" className={`rounded-full px-3 py-1 text-xs font-semibold ${locked ? "bg-emerald-900 text-white" : "bg-amber-100 text-amber-800"}`}>{locked ? <><Lock className="me-1 inline h-3 w-3" />{t("approved")}</> : t("draft")}</span>
        {!locked && <>
          <Button variant="outline" size="sm" onClick={revalidate} disabled={!!busy} data-testid="tailor-revalidate">{busy === "reval" ? <Spinner className="me-1" /> : <RefreshCw className="me-1 h-3.5 w-3.5" />}{t("Re-check")}</Button>
          <Button size="sm" onClick={approve} disabled={!!busy || open > 0} className="bg-emerald-900 hover:bg-emerald-800" data-testid="tailor-approve">{busy === "approve" ? <Spinner className="me-1" /> : <ShieldCheck className="me-1 h-3.5 w-3.5" />}{open ? t("Resolve {n} flags to approve", { n: open }) : t("Approve")}</Button></>}
        {locked && <div className="flex flex-wrap gap-2">
          {[["pdf", "cv", "CV PDF"], ["docx", "cv", "CV DOCX"], ["pdf", "cover", "Cover PDF"], ["docx", "cover", "Cover DOCX"]].map(([fmt, doc, label]) => (
            <Button key={label} size="sm" variant="outline" onClick={() => exp(fmt, doc)} data-testid={`export-${doc}-${fmt}`}><Download className="me-1 h-3.5 w-3.5" />{t(label)}</Button>))}</div>}
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Tabs defaultValue="diff">
          <TabsList className="bg-white"><TabsTrigger value="diff" data-testid="tab-diff">{t("Changes vs master")}</TabsTrigger>
            <TabsTrigger value="edit" data-testid="tab-edit">{t("Edit CV")}</TabsTrigger><TabsTrigger value="cover" data-testid="tab-cover">{t("Cover letter")}</TabsTrigger></TabsList>
          <TabsContent value="diff" className="mt-4 space-y-4"><Diff master={cvToText(tl.master, t)} tailored={cvToText(cv, t)} />
            {tl.changes?.length > 0 && <Card><div className="jp-eyebrow mb-2">{t("What the AI changed")}</div><ul className="list-disc space-y-1 ps-5 text-sm text-slate-700">{tl.changes.map((c, i) => <li key={i}>{c}</li>)}</ul></Card>}</TabsContent>
          <TabsContent value="edit" className="mt-4"><Card>{locked ? <p className="text-sm text-slate-500">{t("Approved versions are locked. Tailor again to make changes.")}</p> : <>
            <CVEditor value={cv} onChange={setCv} /><Button className="mt-4 bg-emerald-900 hover:bg-emerald-800" onClick={saveEdits} disabled={!!busy} data-testid="tailor-save-edits"><Save className="me-2 h-4 w-4" />{t("Save edits")}</Button></>}</Card></TabsContent>
          <TabsContent value="cover" className="mt-4"><Card>
            <Textarea rows={16} value={cover} onChange={(e) => setCover(e.target.value)} disabled={locked} data-testid="cover-letter-text" className="leading-relaxed" />
            {!locked && <Button className="mt-3 bg-emerald-900 hover:bg-emerald-800" onClick={saveEdits} disabled={!!busy} data-testid="cover-save">{t("Save edits")}</Button>}</Card></TabsContent>
        </Tabs>
        <aside><Flags tl={tl} onAction={flag} locked={locked} /></aside>
      </div>
    </div>
  );
}
