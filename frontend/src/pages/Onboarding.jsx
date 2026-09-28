import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/lib/i18n";
import { COUNTRIES, TIMEZONES, CITIES } from "@/lib/constants";

export function Field({ label, children, hint }) {
  return <div className="space-y-1.5"><Label className="text-slate-700">{label}</Label>{children}{hint && <p className="text-xs text-slate-400">{hint}</p>}</div>;
}

export function SimpleSelect({ value, onChange, options, testid, placeholder }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger data-testid={testid} className="bg-white"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent className="bg-white">{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
    </Select>
  );
}

export default function Onboarding() {
  const { t, lang, setLang } = useI18n();
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ lang, country: user?.country || "SA", city: user?.city || "", timezone: user?.timezone || "Asia/Riyadh",
    quiet_start: "22:00", quiet_end: "08:00", weekly_goal: 10 });
  const [c, setC] = useState({ terms: false, ai_processing: false, email_messaging: true });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/onboarding", { ...f, weekly_goal: Number(f.weekly_goal), consents: c });
      setUser(data);
      nav("/app/cv");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen bg-[#F8FAFC] jp-grain">
      <div className="mx-auto max-w-2xl px-5 py-10">
        <div className="mb-8 flex items-center gap-2"><div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-900 text-white"><Compass className="h-4 w-4" /></div><span className="font-heading text-lg font-bold">JobPilot</span></div>
        <div className="jp-eyebrow">{t("Setup · 1 minute")}</div>
        <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight">{t("Let's set up your workspace")}</h1>
        <div className="mt-8 space-y-6 rounded-xl border border-slate-200 bg-white p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("Language")}><SimpleSelect testid="onb-lang" value={f.lang} onChange={(v) => { set("lang")(v); setLang(v); }} options={[["en", "English"], ["ar", "العربية"]]} /></Field>
            <Field label={t("Country")}><SimpleSelect testid="onb-country" value={f.country} onChange={set("country")} options={COUNTRIES.map((x) => [x[0], lang === "ar" ? x[2] : x[1]])} /></Field>
            <Field label={t("City")}>
              <Input data-testid="onb-city" list="onb-city-suggestions" value={f.city} onChange={(e) => set("city")(e.target.value)} placeholder={t("e.g. Riyadh")} />
              <datalist id="onb-city-suggestions">{(CITIES[f.country] || []).map(([k, en, ar]) => <option key={k} value={lang === "ar" ? ar : en} />)}</datalist>
            </Field>
            <Field label={t("Timezone")}><SimpleSelect testid="onb-timezone" value={f.timezone} onChange={set("timezone")} options={TIMEZONES.map((z) => [z, z])} /></Field>
            <Field label={t("Quiet hours start")}><Input data-testid="onb-quiet-start" type="time" value={f.quiet_start} onChange={(e) => set("quiet_start")(e.target.value)} /></Field>
            <Field label={t("Quiet hours end")}><Input data-testid="onb-quiet-end" type="time" value={f.quiet_end} onChange={(e) => set("quiet_end")(e.target.value)} /></Field>
            <Field label={t("Weekly application goal")}><Input data-testid="onb-weekly-goal" type="number" min={1} max={100} value={f.weekly_goal} onChange={(e) => set("weekly_goal")(e.target.value)} /></Field>
          </div>
          <div className="space-y-3 border-t pt-5">
            {[["terms", <>{t("I accept the")} <Link to="/legal/terms" target="_blank" className="text-emerald-800 underline">{t("Terms")}</Link> {t("and")} <Link to="/legal/privacy" target="_blank" className="text-emerald-800 underline">{t("Privacy policy")}</Link> *</>],
              ["ai_processing", <>{t("I consent to AI processing of my CV and job data (providers may process data outside the Kingdom; never used for training).")} *</>],
              ["email_messaging", t("Send me reminders and job alerts by email (optional).")]].map(([k, label]) => (
              <label key={k} className="flex items-start gap-3 text-sm text-slate-700">
                <Checkbox data-testid={`consent-${k}`} checked={c[k]} onCheckedChange={(v) => setC({ ...c, [k]: !!v })} className="mt-0.5" /><span>{label}</span>
              </label>))}
          </div>
          <Button data-testid="onboarding-submit" disabled={busy || !c.terms || !c.ai_processing} onClick={submit} className="w-full bg-emerald-900 hover:bg-emerald-800">{t("Continue to CV upload")}</Button>
        </div>
      </div>
    </div>
  );
}
