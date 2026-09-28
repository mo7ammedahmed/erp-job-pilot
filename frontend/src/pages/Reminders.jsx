import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Check, Clock, Trash2, Moon, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Card, FullLoader, Empty } from "@/components/common";

const SNOOZE = [[60, "1h"], [1440, "1d"], [10080, "1w"]];

function Row({ r, onDone, onSnooze, onDelete }) {
  const { t, fmtDateTime } = useI18n();
  return (
    <li className="flex flex-wrap items-center gap-3 py-3" data-testid={`reminder-${r.reminder_id}`}>
      <div className="min-w-0 flex-1"><div className={`text-sm ${r.status === "done" ? "text-slate-400 line-through" : "text-slate-900"}`}>{r.title}</div>
        <div className="font-mono text-xs text-slate-500">{fmtDateTime(r.due_at)} · {t(r.type)} {r.channels ? `· ${r.channels.join(", ")}` : ""}
          {r.application_id && <Link to={`/app/tracker?app=${r.application_id}`} className="ms-2 text-emerald-800 underline">{t("Open")}</Link>}</div></div>
      {r.status !== "done" && <div className="flex items-center gap-1">
        <Button size="sm" variant="outline" className="h-7" onClick={() => onDone(r)} data-testid={`reminder-done-${r.reminder_id}`}><Check className="me-1 h-3 w-3" />{t("Done")}</Button>
        {SNOOZE.map(([m, l]) => <Button key={l} size="sm" variant="ghost" className="h-7 px-2 font-mono text-xs" onClick={() => onSnooze(r, m)} data-testid={`reminder-snooze-${l}-${r.reminder_id}`}><Clock className="me-1 h-3 w-3" />{l}</Button>)}</div>}
      <button onClick={() => onDelete(r)} data-testid={`reminder-delete-${r.reminder_id}`}><Trash2 className="h-3.5 w-3.5 text-slate-400" /></button>
    </li>
  );
}

export default function Reminders() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [items, setItems] = useState(null);
  const [f, setF] = useState({ title: "", due_at: "" });
  const load = () => api.get("/reminders").then((r) => setItems(r.data));
  useEffect(() => { load(); }, []);
  const act = (p) => p.then(load).catch((e) => toast.error(errMsg(e)));
  const create = () => act(api.post("/reminders", { title: f.title, due_at: new Date(f.due_at).toISOString() }).then(() => setF({ title: "", due_at: "" })));
  if (!items) return <FullLoader />;
  const groups = [["Needs action", items.filter((r) => r.status === "sent")], ["Upcoming", items.filter((r) => ["pending", "snoozed"].includes(r.status))], ["Done", items.filter((r) => r.status === "done").slice(-20)]];
  const handlers = { onDone: (r) => act(api.post(`/reminders/${r.reminder_id}/done`)), onSnooze: (r, m) => act(api.post(`/reminders/${r.reminder_id}/snooze`, { minutes: m })), onDelete: (r) => act(api.delete(`/reminders/${r.reminder_id}`)) };
  return (
    <div>
      <PageHeader eyebrow={t("Reminders")} title={t("Follow-ups & interview prep")} subtitle={t("Rules: follow up {n} days after applying · interview prep 24h and 1h before · deadline 2 days before.", { n: user?.followup_days || 7 })} />
      <div className="mb-4 flex items-center gap-2 text-xs text-slate-500" data-testid="quiet-hours-indicator"><Moon className="h-3.5 w-3.5" />{t("Quiet hours {a}–{b} ({tz}). Reminders due then arrive when quiet hours end.", { a: user?.quiet_start, b: user?.quiet_end, tz: user?.timezone })}</div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">{groups.map(([title, list]) => (
          <Card key={title}><div className="jp-eyebrow">{t(title)} · {list.length}</div>
            {list.length === 0 ? <p className="py-3 text-sm text-slate-400">{t("Nothing here.")}</p> : <ul className="divide-y">{list.map((r) => <Row key={r.reminder_id} r={r} {...handlers} />)}</ul>}</Card>))}
          {items.length === 0 && <Empty title={t("No reminders yet")} text={t("Move an application to Applied or set an interview date and reminders are created automatically.")} />}
        </div>
        <Card className="h-fit"><div className="mb-3 font-heading font-semibold">{t("Custom reminder")}</div>
          <div className="space-y-2"><Input data-testid="reminder-title" placeholder={t("e.g. Prepare portfolio")} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
            <Input data-testid="reminder-due" type="datetime-local" value={f.due_at} onChange={(e) => setF({ ...f, due_at: e.target.value })} />
            <Button data-testid="reminder-create" disabled={!f.title || !f.due_at} onClick={create} className="w-full bg-emerald-900 hover:bg-emerald-800"><Plus className="me-2 h-4 w-4" />{t("Add reminder")}</Button></div></Card>
      </div>
    </div>
  );
}
