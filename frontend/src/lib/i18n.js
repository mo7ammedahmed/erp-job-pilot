import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { AR } from "./ar";

const I18nCtx = createContext(null);

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(localStorage.getItem("jp_lang") || "en");
  useEffect(() => {
    localStorage.setItem("jp_lang", lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  const t = useCallback((s, vars) => {
    let out = (lang === "ar" && AR[s]) || s;
    if (vars) Object.entries(vars).forEach(([k, v]) => (out = out.replace(`{${k}}`, v)));
    return out;
  }, [lang]);
  const locale = lang === "ar" ? "ar-SA-u-ca-gregory" : "en-GB";
  const fmtDate = useCallback((d, opts = { day: "numeric", month: "short", year: "numeric" }) =>
    d ? new Intl.DateTimeFormat(locale, opts).format(new Date(d)) : "—", [locale]);
  const fmtDateTime = useCallback((d) => fmtDate(d, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }), [fmtDate]);
  const fmtNum = useCallback((n) => (n == null ? "—" : new Intl.NumberFormat(locale).format(n)), [locale]);
  return (
    <I18nCtx.Provider value={{ lang, setLang, t, fmtDate, fmtDateTime, fmtNum, rtl: lang === "ar" }}>
      {children}
    </I18nCtx.Provider>
  );
}

export const useI18n = () => useContext(I18nCtx);
