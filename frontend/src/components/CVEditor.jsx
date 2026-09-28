import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

const LISTS = {
  experience: [["company", "Company"], ["title", "Title"], ["location", "Location"], ["start", "Start"], ["end", "End"]],
  education: [["institution", "Institution"], ["degree", "Degree"], ["field", "Field"], ["start", "Start"], ["end", "End"]],
  projects: [["name", "Name"], ["description", "Description"]],
  languages: [["name", "Language"], ["level", "Level"]],
  certifications: [["name", "Name"], ["issuer", "Issuer"], ["year", "Year"]],
};
const SECTION = { experience: "Experience", education: "Education", projects: "Projects", languages: "Languages", certifications: "Certifications" };

function ListSection({ k, items, onChange }) {
  const { t } = useI18n();
  const fields = LISTS[k];
  const upd = (i, patch) => onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const blank = Object.fromEntries(fields.map(([f]) => [f, ""]));
  return (
    <div className="space-y-3" data-testid={`cv-section-${k}`}>
      <div className="flex items-center justify-between"><h3 className="font-heading font-semibold">{t(SECTION[k])}</h3>
        <Button type="button" size="sm" variant="ghost" onClick={() => onChange([...items, k === "experience" ? { ...blank, bullets: [] } : blank])} data-testid={`cv-add-${k}`}><Plus className="me-1 h-3.5 w-3.5" />{t("Add")}</Button></div>
      {items.map((it, i) => it && (
        <div key={i} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
          <div className="grid gap-2 sm:grid-cols-2">
            {fields.map(([f, label]) => <Input key={f} placeholder={t(label)} value={it[f] || ""} onChange={(e) => upd(i, { [f]: e.target.value })} className="bg-white" data-testid={`cv-${k}-${i}-${f}`} />)}
          </div>
          {k === "experience" && <Textarea className="mt-2 bg-white" rows={4} placeholder={t("One bullet per line")} value={(it.bullets || []).filter((b) => b != null).join("\n")}
            onChange={(e) => upd(i, { bullets: e.target.value.split("\n") })} data-testid={`cv-experience-${i}-bullets`} />}
          <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="mt-2 flex items-center gap-1 text-xs text-rose-600 hover:underline"><Trash2 className="h-3 w-3" />{t("Remove")}</button>
        </div>))}
    </div>
  );
}

export default function CVEditor({ value, onChange }) {
  const { t } = useI18n();
  const cv = value || {};
  const set = (patch) => onChange({ ...cv, ...patch });
  const contact = cv.contact || {};
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2">
        <Input placeholder={t("Full name")} value={cv.name || ""} onChange={(e) => set({ name: e.target.value })} data-testid="cv-name" />
        <Input placeholder={t("Headline")} value={cv.headline || ""} onChange={(e) => set({ headline: e.target.value })} data-testid="cv-headline" />
        {["email", "phone", "location"].map((f) => <Input key={f} placeholder={t(f[0].toUpperCase() + f.slice(1))} value={contact[f] || ""} onChange={(e) => set({ contact: { ...contact, [f]: e.target.value } })} data-testid={`cv-contact-${f}`} />)}
        <Input placeholder={t("Links (comma separated)")} value={(contact.links || []).join(", ")} onChange={(e) => set({ contact: { ...contact, links: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) } })} />
      </div>
      <div><h3 className="mb-2 font-heading font-semibold">{t("Summary")}</h3><Textarea rows={4} value={cv.summary || ""} onChange={(e) => set({ summary: e.target.value })} data-testid="cv-summary" /></div>
      <ListSection k="experience" items={cv.experience || []} onChange={(v) => set({ experience: v })} />
      <div><h3 className="mb-2 font-heading font-semibold">{t("Skills")}</h3>
        <Textarea rows={2} placeholder={t("Comma separated")} value={(cv.skills || []).filter((s) => s != null).join(", ")} onChange={(e) => set({ skills: e.target.value.split(",").map((s) => s.trimStart()) })} data-testid="cv-skills" /></div>
      {["education", "projects", "languages", "certifications"].map((k) => <ListSection key={k} k={k} items={cv[k] || []} onChange={(v) => set({ [k]: v })} />)}
    </div>
  );
}

export function cleanCV(cv) {
  const c = JSON.parse(JSON.stringify(cv || {}));
  c.skills = (c.skills || []).map((s) => (s || "").trim()).filter(Boolean);
  (c.experience || []).forEach((e) => e && (e.bullets = (e.bullets || []).map((b) => (b || "").trim()).filter(Boolean)));
  return c;
}

export function cvToText(cv, t = (s) => s) {
  if (!cv) return "";
  const out = [cv.name, cv.headline, cv.summary && `\n${t("Summary")}\n${cv.summary}`];
  (cv.experience || []).filter(Boolean).forEach((e) => out.push(`\n${e.title || ""} — ${e.company || ""} (${e.start || ""} – ${e.end || ""})`, ...(e.bullets || []).filter(Boolean).map((b) => `• ${b}`)));
  if (cv.skills?.length) out.push(`\n${t("Skills")}\n${cv.skills.filter(Boolean).join(", ")}`);
  (cv.education || []).filter(Boolean).forEach((e) => out.push(`${e.degree || ""} ${e.field || ""} — ${e.institution || ""}`));
  (cv.projects || []).filter(Boolean).forEach((p) => out.push(`${p.name}: ${p.description || ""}`));
  return out.filter(Boolean).join("\n");
}
