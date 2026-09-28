import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UserPlus, X, MessageSquare, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { STATUSES, STATUS_LABEL, STATUS_DOT } from "@/lib/constants";
import { PageHeader, Card, FullLoader, Empty } from "@/components/common";

function CandidateApps({ cand }) {
  const { t, fmtDate } = useI18n();
  const [apps, setApps] = useState(null);
  const [text, setText] = useState({});
  const load = () => api.get(`/coach/candidates/${cand.user_id}/applications`).then((r) => setApps(r.data));
  useEffect(() => { load(); }, [cand.user_id]); // eslint-disable-line
  const send = (aid) => api.post(`/coach/candidates/${cand.user_id}/applications/${aid}/comments`, { text: text[aid] })
    .then(() => { setText({ ...text, [aid]: "" }); toast.success(t("Comment sent")); load(); }).catch((e) => toast.error(errMsg(e)));
  if (!apps) return <FullLoader />;
  if (!apps.length) return <Empty title={t("No applications yet.")} />;
  return (
    <div className="space-y-3" data-testid="coach-candidate-apps">{apps.map((a) => (
      <Card key={a.application_id} className="p-4">
        <div className="flex flex-wrap items-center gap-2"><span className={`h-2 w-2 rounded-full ${STATUS_DOT[a.status]}`} /><span className="font-semibold">{a.title}</span><span className="text-sm text-slate-500">· {a.company}</span>
          <span className="ms-auto text-xs text-slate-400">{t(STATUS_LABEL[a.status])} · {fmtDate(a.updated_at)}</span></div>
        {(a.coach_comments || []).map((c) => <div key={c.comment_id} className="mt-2 rounded bg-emerald-50 p-2 text-sm"><b>{c.coach_name}:</b> {c.text}</div>)}
        <div className="mt-2 flex gap-2"><Input data-testid={`coach-comment-${a.application_id}`} placeholder={t("Leave a comment for your candidate…")} value={text[a.application_id] || ""} onChange={(e) => setText({ ...text, [a.application_id]: e.target.value })} />
          <Button size="sm" variant="outline" disabled={!text[a.application_id]} onClick={() => send(a.application_id)} data-testid={`coach-comment-send-${a.application_id}`}><MessageSquare className="h-4 w-4" /></Button></div>
      </Card>))}</div>
  );
}

export default function Coach() {
  const { t, fmtDate } = useI18n();
  const [d, setD] = useState(null);
  const [email, setEmail] = useState("");
  const [sel, setSel] = useState(null);
  const load = () => api.get("/coach/overview").then((r) => setD(r.data));
  useEffect(() => { load(); }, []);
  const grant = () => api.post("/coach/grant", { coach_email: email }).then(() => { setEmail(""); toast.success(t("Access shared")); load(); }).catch((e) => toast.error(errMsg(e)));
  if (!d) return <FullLoader />;
  return (
    <div>
      <PageHeader eyebrow={t("Coaching")} title={t("Coaching")} subtitle={t("Share your tracker with a career coach, or coach other candidates.")} />
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <Card data-testid="my-coaches"><div className="mb-2 font-heading font-semibold">{t("My coaches")}</div>
            <p className="mb-3 text-xs text-slate-500">{t("Coaches can see your applications (not your files or contacts) and leave comments. Revoke anytime.")}</p>
            <div className="flex gap-2"><Input data-testid="coach-email-input" placeholder="coach@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <Button onClick={grant} disabled={!email} data-testid="coach-grant-button" className="bg-emerald-900 hover:bg-emerald-800"><UserPlus className="h-4 w-4" /></Button></div>
            {d.coaches.map((c) => <div key={c.user_id} className="mt-2 flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm"><span>{c.name} <span className="text-xs text-slate-500">{c.email}</span></span>
              <button onClick={() => api.delete(`/coach/grant/${c.user_id}`).then(load)} data-testid={`coach-revoke-${c.user_id}`}><X className="h-4 w-4 text-slate-400" /></button></div>)}
          </Card>
          <Card data-testid="my-candidates"><div className="mb-2 flex items-center gap-2 font-heading font-semibold"><Users className="h-4 w-4 text-emerald-800" />{t("My candidates")}</div>
            {d.candidates.length === 0 && <p className="text-xs text-slate-500">{t("Candidates who share access with you appear here.")}</p>}
            {d.candidates.map((c) => (
              <button key={c.user_id} onClick={() => setSel(c)} data-testid={`coach-candidate-${c.email}`} className={`mt-1 block w-full rounded-md px-3 py-2 text-start text-sm hover:bg-slate-50 ${sel?.user_id === c.user_id ? "bg-emerald-50" : ""}`}>
                <div className="font-medium">{c.name}</div>
                <div className="font-mono text-[11px] text-slate-500">{STATUSES.filter((s) => c.by_status[s]).map((s) => `${t(STATUS_LABEL[s])} ${c.by_status[s]}`).join(" · ") || "—"}</div>
                {c.last_activity && <div className="text-[11px] text-slate-400">{fmtDate(c.last_activity)}</div>}
              </button>))}
          </Card>
        </aside>
        <section>{sel ? <><div className="mb-3 font-heading text-lg font-semibold">{sel.name}</div><CandidateApps cand={sel} /></> :
          <Empty icon={Users} title={t("Select a candidate")} text={t("Review their pipeline and leave comments on specific applications.")} />}</section>
      </div>
    </div>
  );
}
