import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Check, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, Card, FullLoader, Meter, Spinner } from "@/components/common";
import MoyasarCheckout from "@/components/MoyasarCheckout";

const FEAT = { email_reminders: "Email reminders", gmail: "Gmail drafts & sending", auto_review: "Auto AI review of new matches", whatsapp: "WhatsApp reminders (Phase 2)", priority_ai: "Priority AI" };
const lim = (n, t) => (n < 0 ? t("Unlimited") : n);

export default function Billing() {
  const { t, lang, fmtNum, fmtDate } = useI18n();
  const { refresh } = useAuth();
  const [sp, setSp] = useSearchParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");
  const [moyasarPlan, setMoyasarPlan] = useState(null);
  const load = () => api.get("/billing/plans").then((r) => setD(r.data));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const sid = sp.get("session_id");
    if (!sid) return;
    let n = 0;
    const poll = async () => {
      const { data } = await api.get(`/billing/status/${sid}`);
      if (data.payment_status === "paid") { toast.success(t("Payment confirmed — plan upgraded")); setSp({}); load(); refresh(); }
      else if (n++ < 10) setTimeout(poll, 2000);
    };
    poll();
  }, []); // eslint-disable-line
  useEffect(() => {
    const oid = sp.get("order_id");
    const pid = sp.get("id");
    if (!oid || !pid) return;
    api.get("/billing/moyasar/verify", { params: { id: pid, order_id: oid } })
      .then(() => { toast.success(t("Payment confirmed — plan upgraded")); load(); refresh(); })
      .catch((e) => toast.error(errMsg(e)))
      .finally(() => setSp({}));
  }, []); // eslint-disable-line
  const upgrade = async (plan_id) => {
    if (d.moyasar_enabled) return setMoyasarPlan(plan_id);
    setBusy(plan_id);
    try { window.location.href = (await api.post("/billing/checkout", { plan_id, origin_url: window.location.origin })).data.checkout_url; }
    catch (e) { toast.error(errMsg(e) === "payments_not_configured" ? t("Online payments are not activated yet. Contact the admin to upgrade.") : errMsg(e)); setBusy(""); }
  };
  if (!d) return <FullLoader />;
  const cur = d.plans.find((p) => p.plan_id === d.current) || d.plans[0];
  return (
    <div>
      <PageHeader eyebrow={t("Plan & usage")} title={t("Plan & usage")} subtitle={t("Usage resets on the 1st of each month. Hitting a limit never deletes your data.")} />
      {(d.is_admin || d.plan_expires_at) && <div className="mb-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900" data-testid="plan-expiry-note">
        {d.is_admin ? t("Admin accounts always use the Premium plan.") : t("Your {p} plan is active until {date}, then returns to Free.", { p: cur.name, date: fmtDate(d.plan_expires_at) })}</div>}
      <Card className="mb-6 grid gap-5 sm:grid-cols-4" data-testid="usage-meters">
        <Meter testid="meter-reviews" label={t("AI job reviews")} used={d.usage.reviews} limit={cur.limits.reviews} />
        <Meter testid="meter-tailors" label={t("Tailored CVs")} used={d.usage.tailors} limit={cur.limits.tailors} />
        <Meter testid="meter-cvs" label={t("CV uploads")} used={d.usage.parses} limit={cur.limits.cvs} />
        <Meter testid="meter-applications" label={t("Tracked applications")} used={d.applications} limit={cur.limits.applications} />
      </Card>
      {!d.payments_enabled && !d.moyasar_enabled && <div className="mb-4 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" data-testid="payments-disabled-note"><Info className="h-4 w-4" />{t("Online payments are not activated yet. Contact the admin to upgrade.")}</div>}
      {d.moyasar_enabled && <div className="mb-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-700" data-testid="moyasar-note">{t("Pay in SAR with mada, Apple Pay or STC Pay. Each payment adds one month.")}</div>}
      <MoyasarCheckout planId={moyasarPlan} onClose={() => setMoyasarPlan(null)} />
      <div className="grid gap-4 md:grid-cols-3">{d.plans.map((p) => {
        const isCur = p.plan_id === d.current;
        const hi = p.plan_id === "pro";
        return (
          <div key={p.plan_id} data-testid={`plan-card-${p.plan_id}`} className={`rounded-xl border p-6 ${hi ? "border-emerald-900 bg-emerald-950 text-white" : "border-slate-200 bg-white"}`}>
            <div className="flex items-center justify-between"><div className="font-heading text-lg font-bold">{p.name}</div>{isCur && <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-xs">{t("Current")}</span>}</div>
            <div className="mt-3 font-mono text-3xl font-semibold">${fmtNum(p.price_usd)}<span className="text-sm opacity-60">/{t("mo")}</span></div>
            <div className="text-xs opacity-60">≈ {fmtNum(p.price_sar)} {lang === "ar" ? "ر.س" : "SAR"}</div>
            <ul className="mt-5 space-y-2 text-sm">
              {[[lim(p.limits.reviews, t), "AI job reviews / month"], [lim(p.limits.tailors, t), "tailored CVs / month"], [lim(p.limits.applications, t), "tracked applications"]].map(([n, l]) => <li key={l} className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-emerald-500" /><span><b className="font-mono">{n}</b> {t(l)}</span></li>)}
              {Object.entries(FEAT).filter(([k]) => p.features[k]).map(([k, l]) => <li key={k} className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-emerald-500" />{t(l)}</li>)}
            </ul>
            {!isCur && p.price_usd > 0 && <Button onClick={() => upgrade(p.plan_id)} disabled={!!busy} data-testid={`upgrade-${p.plan_id}`} className={`mt-6 w-full ${hi ? "bg-white text-emerald-950 hover:bg-emerald-50" : "bg-emerald-900 hover:bg-emerald-800"}`}>{busy === p.plan_id && <Spinner className="me-2" />}{t("Upgrade to {p}", { p: p.name })}</Button>}
          </div>);
      })}</div>
    </div>
  );
}
