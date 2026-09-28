import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { UploadCloud, History, RotateCcw, Save, FileText, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, errMsg, download } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Card, FullLoader, Spinner, Empty } from "@/components/common";
import CVEditor, { cleanCV } from "@/components/CVEditor";

export default function CVVault() {
  const { t, fmtDate } = useI18n();
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [draft, setDraft] = useState(null);
  const [fileId, setFileId] = useState(null);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const [parseError, setParseError] = useState("");
  const input = useRef();
  const load = async () => {
    const { data } = await api.get("/cv");
    setD(data);
    if (data.master) { setDraft(data.master.data); setFileId(data.master.file_id); }
  };
  useEffect(() => { load(); }, []);
  const upload = async (file) => {
    if (!file) return;
    setBusy("upload");
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/cv/upload", fd);
      setFileId(data.file_id);
      if (data.parsed) {
        setDraft(data.parsed);
        toast.success(t("CV parsed. Review the details, then save as master."));
      } else {
        // The file is stored even when AI parsing is unavailable, so start from a blank
        // profile the user fills in by hand and offer a retry.
        setDraft({ name: "", headline: "", contact: { email: user?.email || "", phone: "", location: "", links: [] }, summary: "", experience: [], education: [], skills: [], projects: [], languages: [], certifications: [] });
        setParseError(data.parse_error || t("AI parsing is unavailable right now."));
        toast.warning(t("CV uploaded, but AI parsing is unavailable. Fill in the details by hand."));
      }
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); input.current.value = ""; }
  };
  const reparse = async () => {
    if (!fileId) return;
    setBusy("parse");
    try {
      const { data } = await api.post("/cv/parse", { file_id: fileId });
      setDraft(data.parsed);
      setParseError("");
      toast.success(t("CV parsed. Review the details, then save as master."));
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  const save = async () => {
    setBusy("save");
    try {
      await api.post("/cv/versions", { data: cleanCV(draft), file_id: fileId, note: "" });
      toast.success(t("Master CV saved as a new version"));
      await load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };
  const restore = async (vid) => { await api.post(`/cv/versions/${vid}/restore`); toast.success(t("Version restored")); setPreview(null); load(); };
  const view = async (vid) => setPreview((await api.get(`/cv/versions/${vid}`)).data);
  if (!d) return <FullLoader />;
  return (
    <div>
      <PageHeader eyebrow={t("CV vault")} title={t("Your master CV")} subtitle={t("The single source of truth for every AI review and tailored CV.")}
        actions={<>
          <input ref={input} type="file" accept=".pdf,.docx" className="hidden" onChange={(e) => upload(e.target.files[0])} data-testid="cv-file-input" />
          <Button variant="outline" onClick={() => input.current.click()} disabled={!!busy} data-testid="cv-upload-button">{busy === "upload" ? <Spinner className="me-2" /> : <UploadCloud className="me-2 h-4 w-4" />}{busy === "upload" ? t("Reading your CV…") : t("Upload PDF / DOCX")}</Button>
          {draft && <Button onClick={save} disabled={!!busy} className="bg-emerald-900 hover:bg-emerald-800" data-testid="cv-save-button">{busy === "save" ? <Spinner className="me-2" /> : <Save className="me-2 h-4 w-4" />}{t("Save as master")}</Button>}</>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card>
          {parseError && <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="cv-parse-warning">
            <span className="flex-1">{parseError}</span>
            <Button size="sm" variant="outline" onClick={reparse} disabled={!!busy} data-testid="cv-retry-parse">
              {busy === "parse" && <Spinner className="me-2" />}{t("Retry AI parsing")}
            </Button>
          </div>}
          {draft ? <CVEditor value={draft} onChange={setDraft} /> :
            <button onClick={() => input.current.click()} className="flex w-full flex-col items-center gap-3 rounded-xl border-2 border-dashed border-slate-300 p-12 text-center hover:border-emerald-600 hover:bg-emerald-50/40" data-testid="cv-dropzone">
              <UploadCloud className="h-8 w-8 text-emerald-800" /><div className="font-heading font-semibold">{t("Upload your CV to get started")}</div>
              <div className="text-sm text-slate-500">{t("PDF or DOCX, up to 8 MB. AI extracts your experience, skills and education — you review everything.")}</div></button>}
        </Card>
        <aside className="space-y-4">
          <Card data-testid="cv-versions">
            <div className="mb-3 flex items-center gap-2 font-heading font-semibold"><History className="h-4 w-4 text-emerald-800" />{t("Versions")}</div>
            {d.versions.length === 0 ? <Empty title={t("No versions yet")} /> : <ul className="space-y-1">{d.versions.map((v) => (
              <li key={v.cv_version_id} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-50">
                <FileText className="h-3.5 w-3.5 text-slate-400" />
                <button className="flex-1 text-start" onClick={() => view(v.cv_version_id)} data-testid={`cv-version-${v.version}`}>v{v.version} {v.is_master && <span className="ms-1 rounded bg-emerald-900 px-1.5 text-[10px] text-white">{t("master")}</span>}
                  <div className="text-xs text-slate-400">{fmtDate(v.created_at)} {v.note}</div></button>
                {!v.is_master && <button onClick={() => restore(v.cv_version_id)} title={t("Restore")} data-testid={`cv-restore-${v.version}`}><RotateCcw className="h-3.5 w-3.5 text-slate-500" /></button>}
              </li>))}</ul>}
            {fileId && <Button variant="ghost" size="sm" className="mt-3 w-full" onClick={() => download(`/files/${fileId}`, "original-cv")} data-testid="cv-download-original"><Download className="me-2 h-3.5 w-3.5" />{t("Original file")}</Button>}
          </Card>
          {preview && <Card data-testid="cv-version-preview"><div className="mb-2 font-semibold">v{preview.version}</div>
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs text-slate-600">{preview.data.name}{"\n"}{preview.data.headline}{"\n\n"}{(preview.data.skills || []).join(", ")}</pre>
            {!preview.is_master && <Button size="sm" variant="outline" className="mt-2 w-full" onClick={() => restore(preview.cv_version_id)}>{t("Restore this version")}</Button>}</Card>}
        </aside>
      </div>
    </div>
  );
}
