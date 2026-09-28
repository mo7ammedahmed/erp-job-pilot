import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ baseURL: API, withCredentials: true });

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const cfg = err.config || {};
    const status = err.response?.status;
    if (status === 401 && !cfg._retry && !String(cfg.url).includes("/auth/")) {
      cfg._retry = true;
      refreshing = refreshing || api.post("/auth/refresh").finally(() => (refreshing = null));
      try {
        await refreshing;
        return api(cfg);
      } catch (_) {
        /* fall through */
      }
    }
    const d = err.response?.data?.detail;
    if (status === 402 && d && typeof d === "object") {
      window.dispatchEvent(new CustomEvent("jp:limit", { detail: d }));
    }
    return Promise.reject(err);
  }
);

const LIMIT_LABEL = {
  cvs: "CV uploads",
  parses: "CV uploads",
  reviews: "job reviews",
  tailors: "tailored CVs",
  applications: "applications",
  interview_preps: "interview preps",
};

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (d == null) return e?.message || "Something went wrong. Please try again.";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d.code === "limit_reached") {
    const what = LIMIT_LABEL[d.kind] || d.kind;
    return `You have used all ${d.limit} ${what} included in the ${d.plan} plan. Upgrade from Plan & usage to continue.`;
  }
  if (d.code === "feature_locked") return "Upgrade your plan to use this feature";
  return d.msg || JSON.stringify(d);
}

export async function download(path, filename) {
  const r = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
