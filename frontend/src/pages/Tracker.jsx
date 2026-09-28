import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Plus, LayoutGrid, List, Ghost, StickyNote, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { STATUSES, STATUS_LABEL, STATUS_DOT } from "@/lib/constants";
import { PageHeader, FullLoader } from "@/components/common";
import { SimpleSelect } from "@/pages/Onboarding";
import ApplicationDrawer from "@/pages/ApplicationDrawer";

function KCard({ a, onOpen, onMove }) {
  const { t, fmtDate } = useI18n();
  return (
    <div draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", a.application_id)} onClick={() => onOpen(a.application_id)}
      data-testid={`kanban-card-${a.application_id}`} className="cursor-grab rounded-lg border border-slate-200 bg-white p-3 jp-card-hover active:cursor-grabbing">
      <div className="text-sm font-semibold leading-snug text-slate-900">{a.title || t("Untitled")}</div>
      <div className="mt-0.5 text-xs text-slate-500">{a.company}</div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
        {a.notes?.length > 0 && <span className="flex items-center gap-0.5"><StickyNote className="h-3 w-3" />{a.notes.length}</span>}
        {a.contacts?.length > 0 && <span className="flex items-center gap-0.5"><Users className="h-3 w-3" />{a.contacts.length}</span>}
        {a.interview_at && <span className="rounded bg-amber-50 px-1 text-amber-700">{t("Interview")} {fmtDate(a.interview_at, { day: "numeric", month: "short" })}</span>}
        {a.ghost_suggested && <span className="flex items-center gap-0.5 text-slate-500"><Ghost className="h-3 w-3" />{t("Ghosted?")}</span>}
        <span className="ms-auto font-mono">{fmtDate(a.updated_at, { day: "numeric", month: "short" })}</span>
      </div>
      <div className="mt-2 lg:hidden" onClick={(e) => e.stopPropagation()}>
        <SimpleSelect testid={`kanban-move-${a.application_id}`} value={a.status} onChange={(v) => onMove(a.application_id, v)} options={STATUSES.map((s) => [s, t(STATUS_LABEL[s])])} />
      </div>
    </div>
  );
}

export default function Tracker() {
  const { t, fmtDate } = useI18n();
  const [sp, setSp] = useSearchParams();
  const [apps, setApps] = useState(null);
  const [view, setView] = useState("board");
  const [over, setOver] = useState("");
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ title: "", company: "", url: "", status: "saved" });
  const load = () => api.get("/applications").then((r) => setApps(r.data));
  useEffect(() => { load(); }, []);
  const openId = sp.get("app");
  const openApp = (id) => setSp(id ? { app: id } : {});
  const move = async (id, status) => {
    setApps((p) => p.map((a) => (a.application_id === id ? { ...a, status } : a)));
    try { await api.post(`/applications/${id}/move`, { status }); } catch (e) { toast.error(errMsg(e)); }
    load();
  };
  const add = async () => {
    try { await api.post("/applications", f); setAdding(false); setF({ title: "", company: "", url: "", status: "saved" }); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  if (!apps) return <FullLoader />;
  return (
    <div>
      <PageHeader eyebrow={t("Tracker")} title={t("Applications")} subtitle={t("{n} applications", { n: apps.length })}
        actions={<>
          <div className="flex rounded-lg border border-slate-200 bg-white p-0.5">
            <button onClick={() => setView("board")} data-testid="view-board" className={`rounded-md p-1.5 ${view === "board" ? "bg-emerald-900 text-white" : ""}`}><LayoutGrid className="h-4 w-4" /></button>
            <button onClick={() => setView("list")} data-testid="view-list" className={`rounded-md p-1.5 ${view === "list" ? "bg-emerald-900 text-white" : ""}`}><List className="h-4 w-4" /></button></div>
          <Button onClick={() => setAdding(true)} className="bg-emerald-900 hover:bg-emerald-800" data-testid="tracker-add-button"><Plus className="me-2 h-4 w-4" />{t("Add application")}</Button></>} />
      {view === "board" ? (
        <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6" data-testid="kanban-board">
          {STATUSES.map((s) => {
            const items = apps.filter((a) => a.status === s);
            return (
              <div key={s} data-testid={`kanban-col-${s}`} onDragOver={(e) => { e.preventDefault(); setOver(s); }} onDragLeave={() => setOver("")}
                onDrop={(e) => { setOver(""); move(e.dataTransfer.getData("text/plain"), s); }}
                className={`jp-kanban-col flex w-64 shrink-0 flex-col rounded-xl bg-slate-100/70 p-2 ${over === s ? "drag-over" : ""}`}>
                <div className="flex items-center gap-2 px-2 py-2 text-sm font-semibold"><span className={`h-2 w-2 rounded-full ${STATUS_DOT[s]}`} />{t(STATUS_LABEL[s])}<span className="ms-auto font-mono text-xs text-slate-400">{items.length}</span></div>
                <div className="flex min-h-[120px] flex-col gap-2">{items.map((a) => <KCard key={a.application_id} a={a} onOpen={openApp} onMove={move} />)}</div>
              </div>);
          })}
        </div>) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="tracker-list">
          <table className="w-full text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Role", "Company", "Status", "Source", "Interview", "Updated"].map((h) => <th key={h} className="px-4 py-2 text-start font-medium">{t(h)}</th>)}</tr></thead>
            <tbody>{apps.map((a) => (
              <tr key={a.application_id} onClick={() => openApp(a.application_id)} className="cursor-pointer border-t hover:bg-slate-50">
                <td className="px-4 py-2 font-medium">{a.title}</td><td className="px-4 py-2">{a.company}</td>
                <td className="px-4 py-2"><span className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${STATUS_DOT[a.status]}`} />{t(STATUS_LABEL[a.status])}</span></td>
                <td className="px-4 py-2 capitalize">{a.source}</td><td className="px-4 py-2 font-mono text-xs">{a.interview_at ? fmtDate(a.interview_at) : "—"}</td>
                <td className="px-4 py-2 font-mono text-xs">{fmtDate(a.updated_at)}</td></tr>))}</tbody></table>
          {apps.length === 0 && <div className="p-6 text-sm text-slate-500">{t("No applications yet.")} <Link to="/app/jobs" className="text-emerald-800 underline">{t("Browse jobs")}</Link></div>}
        </div>)}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="bg-white">
          <DialogHeader><DialogTitle>{t("Add application")}</DialogTitle></DialogHeader>
          <Input data-testid="add-app-title" placeholder={t("Role title")} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <Input data-testid="add-app-company" placeholder={t("Company")} value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} />
          <Input data-testid="add-app-url" placeholder={t("Job link (optional)")} value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
          <SimpleSelect testid="add-app-status" value={f.status} onChange={(v) => setF({ ...f, status: v })} options={STATUSES.map((s) => [s, t(STATUS_LABEL[s])])} />
          <Button data-testid="add-app-submit" disabled={!f.title} onClick={add} className="bg-emerald-900 hover:bg-emerald-800">{t("Add")}</Button>
        </DialogContent>
      </Dialog>
      {openId && <ApplicationDrawer id={openId} onClose={() => openApp(null)} onChanged={load} />}
    </div>
  );
}
