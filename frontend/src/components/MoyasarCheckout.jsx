import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api, errMsg } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Spinner } from "@/components/common";

const MPF = "https://cdn.moyasar.com/mpf/1.7.3/moyasar";

function loadMoyasar() {
  if (window.Moyasar) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = `${MPF}.css`;
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = `${MPF}.js`;
    s.onload = resolve;
    s.onerror = reject;
    document.body.appendChild(s);
  });
}

export default function MoyasarCheckout({ planId, onClose }) {
  const { t, lang } = useI18n();
  const [err, setErr] = useState("");
  const [order, setOrder] = useState(null);
  const mounted = useRef(false);
  useEffect(() => {
    if (!planId || mounted.current) return;
    mounted.current = true;
    (async () => {
      try {
        const { data } = await api.post("/billing/moyasar/order", { plan_id: planId });
        setOrder(data);
        await loadMoyasar();
        window.Moyasar.init({
          element: ".mysr-form", amount: data.amount, currency: data.currency, description: data.description,
          publishable_api_key: data.publishable_key, language: lang,
          callback_url: `${window.location.origin}/app/billing?order_id=${data.order_id}`,
          methods: data.apple_pay ? ["creditcard", "stcpay", "applepay"] : ["creditcard", "stcpay"],
          supported_networks: ["mada", "visa", "mastercard"],
          ...(data.apple_pay ? { apple_pay: { country: "SA", label: "JobPilot", validate_merchant_url: "https://api.moyasar.com/v1/applepay/initiate" } } : {}),
        });
      } catch (e) { setErr(errMsg(e)); }
    })();
  }, [planId, lang]);
  return (
    <Dialog open={!!planId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md bg-white" data-testid="moyasar-dialog">
        <DialogHeader><DialogTitle>{t("Pay with mada, Apple Pay or STC Pay")}</DialogTitle>
          <DialogDescription>{order ? `${order.description} · ${(order.amount / 100).toFixed(2)} SAR` : ""}</DialogDescription></DialogHeader>
        {err ? <p className="text-sm text-rose-600" data-testid="moyasar-error">{err}</p> : <>{!order && <Spinner />}<div className="mysr-form" data-testid="moyasar-form" /></>}
        <p className="text-xs text-slate-400">{t("Secure payment by Moyasar. One month of access; renew anytime.")}</p>
      </DialogContent>
    </Dialog>
  );
}
