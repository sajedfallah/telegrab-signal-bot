import {
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  Activity,
  AreaChart as ChartIcon,
  Bell,
  Bot,
  CircleDollarSign,
  ChevronLeft,
  CircleUserRound,
  Download,
  Gauge,
  Headphones,
  LayoutDashboard,
  LogOut,
  Power,
  Menu,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  ServerCog,
  Send,
  Settings2,
  ShieldCheck,
  Signal,
  SlidersHorizontal,
  TrendingUp,
  Users,
  WalletCards,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Page =
  | "dashboard"
  | "users"
  | "signals"
  | "experts"
  | "reports"
  | "notifications"
  | "operations"
  | "risk-center"
  | "commerce"
  | "communications"
  | "security"
  | "audit";
type Json = Record<string, any>;
const API = "/api/v1/admin-web";

const fa = new Intl.NumberFormat("fa-IR");
const money = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });
const date = (value?: string) =>
  value
    ? new Intl.DateTimeFormat("fa-IR", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
const statusFa: Record<string, string> = {
  ACTIVE: "فعال",
  BLOCKED: "مسدود",
  DRAFT: "پیش‌نویس",
  PENDING: "در انتظار",
  CLOSED: "بسته‌شده",
  CANCELED: "لغوشده",
  ADMIN: "مدیر",
  MODERATOR: "ناظر",
  VIP_USER: "کاربر VIP",
  REGULAR_USER: "کاربر عادی",
};

async function request(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem("nexus-admin-token");
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401 && path !== "/auth/login") {
    localStorage.removeItem("nexus-admin-token");
    location.reload();
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "خطا در ارتباط با سرور");
  }
  if (response.status === 204) return null;
  return response.json();
}

async function portalRequest(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem("nexus-user-token");
  const response = await fetch(`${API}/portal${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "خطا در ارتباط با سرور");
  }
  return response.json();
}

function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value.toLowerCase()}`}>
      <i />
      {statusFa[value] || value}
    </span>
  );
}
function Empty({ text = "داده‌ای برای نمایش وجود ندارد" }: { text?: string }) {
  return (
    <div className="empty">
      <ChartIcon />
      <p>{text}</p>
    </div>
  );
}
function Loader() {
  return (
    <div className="loader">
      <span />
      <span />
      <span />
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <section
        className={`modal ${wide ? "modal-wide" : ""}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="بستن">
            <X />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function Field({
  label,
  children,
  full = false,
}: {
  label: string;
  children: ReactNode;
  full?: boolean;
}) {
  return (
    <label className={full ? "field full" : "field"}>
      <span>{label}</span>
      {children}
    </label>
  );
}
function Toast({ message, kind }: { message: string; kind: "ok" | "error" }) {
  return (
    <div className={`toast ${kind}`}>
      {kind === "ok" ? <ShieldCheck /> : <Activity />}
      {message}
    </div>
  );
}

function Login({ onLogin }: { onLogin: (u: Json) => void }) {
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const r = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      localStorage.setItem("nexus-admin-token", r.token);
      onLogin(r.user);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <main className="login-page">
      <div className="login-orbit orbit-a" />
      <div className="login-orbit orbit-b" />
      <section className="login-card">
        <div className="brand-mark">
          <Zap />
          <span>N</span>
        </div>
        <div className="login-title">
          <small>NEXUS CONTROL</small>
          <h1>مرکز فرماندهی معاملات</h1>
          <p>برای ورود به محیط امن مدیریت، اطلاعات حساب ادمین را وارد کنید.</p>
        </div>
        <form onSubmit={submit}>
          <Field label="نام کاربری">
            <input name="username" autoComplete="username" required autoFocus />
          </Field>
          <Field label="رمز عبور">
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              minLength={8}
              required
            />
          </Field>
          {error && <div className="form-error">{error}</div>}
          <button className="primary login-submit" disabled={loading}>
            {loading ? "در حال بررسی…" : "ورود امن"}
            <ChevronLeft />
          </button>
        </form>
        <button
          className="portal-link"
          onClick={() => {
            location.href = "/admin/?portal=user";
          }}
        >
          <CircleUserRound /> ورود به پنل کاربران
        </button>
        <footer>
          <ShieldCheck /> ارتباط رمزنگاری‌شده و محافظت‌شده
        </footer>
      </section>
    </main>
  );
}

const nav: { key: Page; label: string; icon: any }[] = [
  { key: "dashboard", label: "نمای کلی", icon: LayoutDashboard },
  { key: "operations", label: "عملیات زنده", icon: Gauge },
  { key: "risk-center", label: "مرکز ریسک", icon: SlidersHorizontal },
  { key: "users", label: "کاربران", icon: Users },
  { key: "signals", label: "سیگنال‌ها", icon: Signal },
  { key: "experts", label: "اکسپرت‌ها", icon: Bot },
  { key: "reports", label: "گزارش‌ها و آمار", icon: ChartIcon },
  { key: "commerce", label: "مالی و اشتراک", icon: CircleDollarSign },
  { key: "communications", label: "پشتیبانی و پیام‌ها", icon: Headphones },
  { key: "notifications", label: "مرکز اطلاع‌رسانی", icon: Bell },
  { key: "security", label: "امنیت و سلامت", icon: ServerCog },
  { key: "audit", label: "رویدادهای امنیتی", icon: ShieldCheck },
];

function Shell({
  user,
  page,
  setPage,
  children,
  live,
  onLogout,
}: {
  user: Json;
  page: Page;
  setPage: (p: Page) => void;
  children: ReactNode;
  live: boolean;
  onLogout: () => void;
}) {
  const [mobile, setMobile] = useState(false);
  return (
    <div className="app-shell">
      <aside className={mobile ? "open" : ""}>
        <div className="sidebar-brand">
          <div className="brand-mark small">
            <Zap />
            <span>N</span>
          </div>
          <div>
            <b>NEXUS</b>
            <small>ADMIN CONSOLE</small>
          </div>
          <button
            className="icon-btn mobile-only"
            onClick={() => setMobile(false)}
          >
            <X />
          </button>
        </div>
        <nav>
          {nav.map((n) => (
            <button
              key={n.key}
              className={page === n.key ? "active" : ""}
              onClick={() => {
                setPage(n.key);
                setMobile(false);
              }}
            >
              <n.icon />
              <span>{n.label}</span>
              {n.key === "signals" && <em>LIVE</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="system-health">
            <span className={live ? "pulse" : "pulse off"} />
            <div>
              <b>{live ? "همه سیستم‌ها فعال" : "اتصال لحظه‌ای قطع"}</b>
              <small>آخرین بررسی: همین حالا</small>
            </div>
          </div>
          <button className="profile">
            <CircleUserRound />
            <div>
              <b>{user.display_name}</b>
              <small>{statusFa[user.role] || user.role}</small>
            </div>
            <MoreHorizontal />
          </button>
        </div>
      </aside>
      {mobile && (
        <div className="aside-shade" onClick={() => setMobile(false)} />
      )}
      <main className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setMobile(true)}>
            <Menu />
          </button>
          <div className="top-search">
            <Search />
            <input placeholder="جستجو در پنل…" />
          </div>
          <div className="top-actions">
            <span className="live-chip">
              <i /> داده زنده
            </span>
            <button className="icon-btn">
              <Bell />
            </button>
            <button className="icon-btn" onClick={onLogout} title="خروج">
              <LogOut />
            </button>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

function PageHead({
  eyebrow,
  title,
  subtitle,
  action,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        <small>{eyebrow}</small>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
function Kpi({
  title,
  value,
  meta,
  icon: Icon,
  tone,
}: {
  title: string;
  value: string;
  meta: string;
  icon: any;
  tone: string;
}) {
  return (
    <article className={`kpi ${tone}`}>
      <div className="kpi-top">
        <span>{title}</span>
        <div>
          <Icon />
        </div>
      </div>
      <strong>{value}</strong>
      <small>{meta}</small>
      <div className="kpi-glow" />
    </article>
  );
}

function Dashboard({
  data,
  refresh,
}: {
  data: Json | null;
  refresh: () => void;
}) {
  if (!data) return <Loader />;
  const pie = [
    { name: "موفق", value: data.signals.wins || 0, color: "#13d9a3" },
    {
      name: "سایر",
      value: Math.max((data.signals.closed || 0) - (data.signals.wins || 0), 0),
      color: "#ff647c",
    },
  ];
  return (
    <>
      <PageHead
        eyebrow="اتاق عملیات"
        title="نمای کلی سیستم"
        subtitle="سلام؛ اینجا نبض زنده کاربران، سیگنال‌ها و اکسپرت‌های NEXUS را می‌بینید."
        action={
          <button className="ghost" onClick={refresh}>
            <RefreshCw /> بروزرسانی
          </button>
        }
      />
      <section className="kpi-grid">
        <Kpi
          title="کل کاربران"
          value={fa.format(data.users.users || 0)}
          meta={`${fa.format(data.users.vip_users || 0)} عضو VIP`}
          icon={Users}
          tone="cyan"
        />
        <Kpi
          title="سیگنال‌های باز"
          value={fa.format(data.signals.active || 0)}
          meta={`${fa.format(data.signals.total || 0)} سیگنال ثبت‌شده`}
          icon={Signal}
          tone="violet"
        />
        <Kpi
          title="سود خالص ثبت‌شده"
          value={`$${money.format(data.profit.profit || 0)}`}
          meta={`${fa.format(data.profit.traders || 0)} معامله‌گر`}
          icon={TrendingUp}
          tone="green"
        />
        <Kpi
          title="اکسپرت آنلاین"
          value={`${fa.format(data.experts.online || 0)} / ${fa.format(data.experts.total || 0)}`}
          meta="اتصال در دو دقیقه اخیر"
          icon={Bot}
          tone="orange"
        />
      </section>
      <section className="dashboard-grid">
        <article className="panel performance">
          <div className="panel-head">
            <div>
              <small>روند هفت‌روزه</small>
              <h2>عملکرد سیگنال‌ها</h2>
            </div>
            <span className="delta">+{fa.format(data.win_rate)}٪ برد</span>
          </div>
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.trend}>
                <defs>
                  <linearGradient id="signalFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#51d9ff" stopOpacity={0.35} />
                    <stop offset="1" stopColor="#51d9ff" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#172a3f" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#668099"
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis stroke="#668099" />
                <Tooltip
                  contentStyle={{
                    background: "#0b1828",
                    border: "1px solid #1b334a",
                    borderRadius: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="signals"
                  stroke="#51d9ff"
                  strokeWidth={3}
                  fill="url(#signalFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>
        <article className="panel win-card">
          <div className="panel-head">
            <div>
              <small>کیفیت اجرا</small>
              <h2>نرخ موفقیت</h2>
            </div>
          </div>
          <div className="donut">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pie}
                  innerRadius={68}
                  outerRadius={86}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {pie.map((x) => (
                    <Cell key={x.name} fill={x.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div>
              <strong>{fa.format(data.win_rate)}٪</strong>
              <span>Win Rate</span>
            </div>
          </div>
          <div className="legend">
            <span>
              <i className="green-dot" /> موفق{" "}
              {fa.format(data.signals.wins || 0)}
            </span>
            <span>
              <i className="red-dot" /> ناموفق{" "}
              {fa.format(
                Math.max(
                  (data.signals.closed || 0) - (data.signals.wins || 0),
                  0,
                ),
              )}
            </span>
          </div>
        </article>
        <article className="panel activity-panel">
          <div className="panel-head">
            <div>
              <small>ثبت تغییرات</small>
              <h2>آخرین فعالیت‌ها</h2>
            </div>
          </div>
          <div className="timeline">
            {data.recent_activity.length ? (
              data.recent_activity.map((a: Json) => (
                <div key={a.id}>
                  <span>
                    <Activity />
                  </span>
                  <div>
                    <b>{a.action.replaceAll("_", " ")}</b>
                    <p>{a.details || `شناسه هدف: ${a.target_id || "—"}`}</p>
                    <small>{date(a.created_at)}</small>
                  </div>
                </div>
              ))
            ) : (
              <Empty />
            )}
          </div>
        </article>
        <article className="panel quick-panel">
          <div className="panel-head">
            <div>
              <small>وضعیت سرویس</small>
              <h2>سلامت زیرساخت</h2>
            </div>
          </div>
          <div className="health-row">
            <span>FastAPI Gateway</span>
            <b>
              <i /> عملیاتی
            </b>
          </div>
          <div className="health-row">
            <span>Telegram Delivery</span>
            <b>
              <i /> آماده
            </b>
          </div>
          <div className="health-row">
            <span>MT5 Live Sync</span>
            <b>
              <i /> متصل
            </b>
          </div>
          <div className="health-row">
            <span>SQLite WAL</span>
            <b>
              <i /> پایدار
            </b>
          </div>
        </article>
      </section>
    </>
  );
}

function UsersPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null),
    [q, setQ] = useState(""),
    [role, setRole] = useState(""),
    [selected, setSelected] = useState<Json | null>(null),
    [activity, setActivity] = useState<Json | null>(null);
  const load = useCallback(
    () =>
      request(`/users?q=${encodeURIComponent(q)}&role=${role}`)
        .then(setData)
        .catch((e) => toast(e.message, "error")),
    [q, role],
  );
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  async function open(u: Json) {
    setSelected(u);
    setActivity(null);
    try {
      setActivity(await request(`/users/${u.telegram_id}/activity`));
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    const f = new FormData(e.currentTarget);
    try {
      await request(`/users/${selected.telegram_id}`, {
        method: "PATCH",
        body: JSON.stringify(Object.fromEntries(f)),
      });
      toast("اطلاعات کاربر ذخیره شد");
      setSelected(null);
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="هویت و دسترسی"
        title="مدیریت کاربران"
        subtitle="جستجو، کنترل نقش و بررسی سابقه کامل اعضای سامانه."
      />
      <div className="toolbar">
        <div className="searchbox">
          <Search />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="نام، نام کاربری یا شناسه تلگرام…"
          />
        </div>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">همه نقش‌ها</option>
          <option value="ADMIN">مدیر</option>
          <option value="MODERATOR">ناظر</option>
          <option value="VIP_USER">VIP</option>
          <option value="REGULAR_USER">عادی</option>
        </select>
        <button className="ghost">
          <SlidersHorizontal /> فیلتر پیشرفته
        </button>
      </div>
      <section className="table-panel">
        <div className="table-meta">
          <span>
            {data ? `${fa.format(data.total)} کاربر` : "در حال دریافت…"}
          </span>
          <small>اطلاعات حساب‌ها به‌صورت زنده از هسته NEXUS</small>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>کاربر</th>
                <th>شناسه تلگرام</th>
                <th>نقش</th>
                <th>اشتراک</th>
                <th>وضعیت</th>
                <th>عضویت</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((u: Json) => (
                <tr key={u.telegram_id}>
                  <td>
                    <div className="user-cell">
                      <span>{(u.first_name || u.username || "?")[0]}</span>
                      <div>
                        <b>{u.first_name || "بدون نام"}</b>
                        <small>@{u.username || "—"}</small>
                      </div>
                    </div>
                  </td>
                  <td className="mono">{u.telegram_id}</td>
                  <td>
                    <Badge value={u.role} />
                  </td>
                  <td>
                    {u.has_license ? (
                      <span className="license-yes">فعال</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <Badge value={u.status} />
                  </td>
                  <td>{date(u.created_at)}</td>
                  <td>
                    <button className="table-action" onClick={() => open(u)}>
                      بررسی <ChevronLeft />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data && <Loader />}
          {data && !data.items.length && <Empty />}
        </div>
      </section>
      {selected && (
        <Modal
          title="پروفایل و سابقه کاربر"
          onClose={() => setSelected(null)}
          wide
        >
          <form className="form-grid" onSubmit={save}>
            <Field label="نام">
              <input
                name="first_name"
                defaultValue={selected.first_name || ""}
              />
            </Field>
            <Field label="نام کاربری">
              <input name="username" defaultValue={selected.username || ""} />
            </Field>
            <Field label="ایمیل">
              <input
                name="email"
                type="email"
                defaultValue={selected.email || ""}
              />
            </Field>
            <Field label="نقش">
              <select name="role" defaultValue={selected.role}>
                <option value="REGULAR_USER">کاربر عادی</option>
                <option value="VIP_USER">کاربر VIP</option>
                <option value="MODERATOR">ناظر</option>
                <option value="ADMIN">مدیر</option>
              </select>
            </Field>
            <Field label="وضعیت">
              <select name="status" defaultValue={selected.status}>
                <option value="ACTIVE">فعال</option>
                <option value="BLOCKED">مسدود</option>
              </select>
            </Field>
            <Field label="یادداشت داخلی" full>
              <textarea
                name="notes"
                rows={3}
                defaultValue={activity?.user?.notes || ""}
              />
            </Field>
            <div className="modal-section full">
              <h3>سابقه اشتراک و فعالیت</h3>
              {activity ? (
                <div className="mini-stats">
                  <span>
                    <b>{fa.format(activity.licenses.length)}</b> اشتراک
                  </span>
                  <span>
                    <b>{fa.format(activity.payments.length)}</b> پرداخت
                  </span>
                  <span>
                    <b>{fa.format(activity.trades.length)}</b> رویداد معامله
                  </span>
                </div>
              ) : (
                <Loader />
              )}
            </div>
            <div className="form-actions full">
              <button
                type="button"
                className="ghost"
                onClick={() => setSelected(null)}
              >
                انصراف
              </button>
              <button className="primary">ذخیره تغییرات</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function SignalForm({
  onDone,
  toast,
}: {
  onDone: () => void;
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [options, setOptions] = useState<Json | null>(null);
  const [market, setMarket] = useState("GOLD");
  const [volumeMode, setVolumeMode] = useState<"RISK" | "FIXED">("RISK");
  const [orderType, setOrderType] = useState("MARKET");
  const [trailing, setTrailing] = useState("");
  useEffect(() => {
    request("/signals/options")
      .then(setOptions)
      .catch((e) => toast(e.message, "error"));
  }, []);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: any = Object.fromEntries(f);
    body.entry_price = +body.entry_price;
    body.stop_loss = +body.stop_loss;
    body.volume_mode = volumeMode;
    body.risk_percent = volumeMode === "RISK" ? +body.risk_percent : 0;
    body.lot_size = volumeMode === "FIXED" ? +body.lot_size : null;
    body.stop_limit_price = orderType.includes("STOP_LIMIT")
      ? +body.stop_limit_price
      : null;
    body.trailing_code = trailing || null;
    body.max_entry_deviation_pct = body.max_entry_deviation_pct
      ? +body.max_entry_deviation_pct
      : null;
    body.max_entry_deviation_abs = body.max_entry_deviation_abs
      ? +body.max_entry_deviation_abs
      : null;
    body.targets = String(body.targets)
      .replaceAll("،", ",")
      .split(",")
      .map(Number)
      .filter(Boolean);
    try {
      await request("/signals", { method: "POST", body: JSON.stringify(body) });
      toast("سیگنال جدید به‌صورت پیش‌نویس ثبت شد");
      onDone();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <form className="form-grid signal-issue-form" onSubmit={submit}>
      <Field label="بازار">
        <select
          name="market_type"
          value={market}
          onChange={(e) => setMarket(e.target.value)}
        >
          <option value="GOLD">فلزات (Gold)</option>
          <option value="FOREX">فارکس</option>
          <option value="CRYPTO">رمزارز</option>
          <option value="INDEX">شاخص‌ها</option>
          <option value="OTHER">انرژی و سایر</option>
        </select>
      </Field>
      <Field label="نماد معاملاتی">
        <select name="symbol" required>
          {(options?.symbols?.[market] || []).map((s: string) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </Field>
      <Field label="جهت">
        <select name="direction">
          <option>BUY</option>
          <option>SELL</option>
        </select>
      </Field>
      <Field label="تایم‌فریم">
        <select name="timeframe" defaultValue="M5">
          {(options?.timeframes || ["M5", "M15", "H1", "H4", "D1"]).map(
            (x: string) => (
              <option key={x}>{x}</option>
            ),
          )}
        </select>
      </Field>
      <Field label="نوع سفارش">
        <select
          name="order_type"
          value={orderType}
          onChange={(e) => setOrderType(e.target.value)}
        >
          {(options?.order_types || ["MARKET"]).map((x: string) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </Field>
      <Field label="نقطه ورود">
        <input name="entry_price" type="number" step="any" required />
      </Field>
      <Field label="حد ضرر">
        <input name="stop_loss" type="number" step="any" required />
      </Field>
      {orderType.includes("STOP_LIMIT") && (
        <Field label="قیمت Stop Limit">
          <input name="stop_limit_price" type="number" step="any" required />
        </Field>
      )}
      <Field label="اهداف (با کاما جدا کنید)" full>
        <input
          name="targets"
          placeholder="۳۴۲۰، ۳۴۳۵، ۳۴۵۰"
          dir="ltr"
          required
        />
      </Field>
      <div className="volume-mode full">
        <button
          type="button"
          className={volumeMode === "RISK" ? "active" : ""}
          onClick={() => setVolumeMode("RISK")}
        >
          <TrendingUp />
          <b>درصد ریسک</b>
          <small>محاسبه حجم بر اساس Balance و فاصله SL</small>
        </button>
        <button
          type="button"
          className={volumeMode === "FIXED" ? "active" : ""}
          onClick={() => setVolumeMode("FIXED")}
        >
          <WalletCards />
          <b>حجم ثابت</b>
          <small>ارسال Lot Size دقیق به اکسپرت</small>
        </button>
      </div>
      {volumeMode === "RISK" ? (
        <Field label="درصد ریسک سیگنال">
          <input
            name="risk_percent"
            type="number"
            min="0.1"
            max="10"
            step=".1"
            defaultValue="1"
            required
          />
        </Field>
      ) : (
        <Field label="حجم ثابت (Lot)">
          <input
            name="lot_size"
            type="number"
            min="0.01"
            max="100"
            step=".01"
            defaultValue="0.01"
            required
          />
        </Field>
      )}
      <Field label="مقصد">
        <select name="destination">
          <option value="BOTH">عمومی + VIP</option>
          <option value="VIP">فقط VIP</option>
          <option value="FREE">عمومی</option>
        </select>
      </Field>
      <Field label="حداکثر انحراف ورود (%)">
        <input
          name="max_entry_deviation_pct"
          type="number"
          min="0.01"
          max="20"
          step=".01"
          placeholder="مثلاً 0.20"
        />
      </Field>
      <Field label="حداکثر انحراف مطلق">
        <input
          name="max_entry_deviation_abs"
          type="number"
          min="0.01"
          step="any"
          placeholder="برای طلا مثلاً 5"
        />
      </Field>
      <Field label="پروفایل تریلینگ" full>
        <select
          name="trailing_code"
          value={trailing}
          onChange={(e) => setTrailing(e.target.value)}
        >
          <option value="">بدون تریلینگ</option>
          {options?.trailing?.map((t: Json) => (
            <option key={t.code} value={t.code}>
              {t.code} — {t.name}
            </option>
          ))}
        </select>
      </Field>
      {trailing && (
        <div className="trailing-preview full">
          <Bot />
          <div>
            <b>
              {options?.trailing?.find((t: Json) => t.code === trailing)?.name}
            </b>
            <p>
              {options?.trailing?.find((t: Json) => t.code === trailing)?.guide}
            </p>
          </div>
        </div>
      )}
      <div className="ea-contract full">
        <ShieldCheck />
        <div>
          <b>اطلاعات ارسالی به اکسپرت MT5</b>
          <span>
            Market، Symbol، Direction، Order Type، Timeframe، Entry، Stop Limit،
            SL، حداکثر ۱۰ TP، Volume Mode، Risk/Lot، Trailing Snapshot و Entry
            Deviation
          </span>
        </div>
      </div>
      <Field label="تحلیل تکنیکال" full>
        <textarea name="technical_analysis" rows={3} />
      </Field>
      <Field label="تحلیل فاندامنتال" full>
        <textarea name="fundamental_analysis" rows={3} />
      </Field>
      <div className="form-actions full">
        <button type="button" className="ghost" onClick={onDone}>
          انصراف
        </button>
        <button className="primary">ثبت پیش‌نویس سیگنال</button>
      </div>
    </form>
  );
}

function SignalsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [create, setCreate] = useState(false),
    [selected, setSelected] = useState<Json | null>(null);
  const load = useCallback(
    () =>
      request(`/signals?q=${encodeURIComponent(q)}&status=${status}`)
        .then(setData)
        .catch((e) => toast(e.message, "error")),
    [q, status],
  );
  useEffect(() => {
    load();
  }, [load]);
  async function changeStatus(id: number, s: string) {
    try {
      await request(`/signals/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: s }),
      });
      toast("وضعیت سیگنال بروزرسانی شد");
      load();
      setSelected(null);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="میز معاملاتی"
        title="مدیریت سیگنال‌ها"
        subtitle="چرخه کامل ایجاد، انتشار، کنترل و بستن سیگنال‌های معاملاتی."
        action={
          <button className="primary" onClick={() => setCreate(true)}>
            <Plus /> سیگنال جدید
          </button>
        }
      />
      <div className="toolbar">
        <div className="searchbox">
          <Search />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="جستجوی نماد یا کد سیگنال…"
          />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">همه وضعیت‌ها</option>
          {["DRAFT", "PENDING", "ACTIVE", "CLOSED", "CANCELED"].map((s) => (
            <option value={s} key={s}>
              {statusFa[s]}
            </option>
          ))}
        </select>
      </div>
      <div className="signal-grid">
        {data?.items.map((s: Json) => (
          <article
            className="signal-card"
            key={s.id}
            onClick={() => setSelected(s)}
          >
            <div className="signal-card-top">
              <div>
                <span
                  className={`direction ${["BUY", "LONG"].includes(s.direction) ? "buy" : "sell"}`}
                >
                  {s.direction}
                </span>
                <b>{s.symbol}</b>
                <small>
                  {s.code} • {s.timeframe}
                </small>
              </div>
              <Badge value={s.status} />
            </div>
            <div className="price-line">
              <div>
                <span>ورود</span>
                <b>{s.entry_price}</b>
              </div>
              <div>
                <span>حد ضرر</span>
                <b className="loss">{s.stop_loss}</b>
              </div>
              <div>
                <span>هدف اول</span>
                <b className="gain">{s.tp1}</b>
              </div>
            </div>
            <footer>
              <span>
                {s.market_type} / {s.category}
              </span>
              <span>{date(s.created_at)}</span>
            </footer>
          </article>
        ))}
        {!data && <Loader />}
        {data && !data.items.length && (
          <Empty text="سیگنالی با این فیلتر پیدا نشد" />
        )}
      </div>
      {create && (
        <Modal
          title="ایجاد سیگنال معاملاتی"
          onClose={() => setCreate(false)}
          wide
        >
          <SignalForm
            toast={toast}
            onDone={() => {
              setCreate(false);
              load();
            }}
          />
        </Modal>
      )}
      {selected && (
        <Modal
          title={`${selected.code} • ${selected.symbol}`}
          onClose={() => setSelected(null)}
          wide
        >
          <div className="signal-detail">
            <div className="detail-hero">
              <div>
                <span>نقطه ورود</span>
                <strong>{selected.entry_price}</strong>
              </div>
              <div>
                <span>حد ضرر</span>
                <strong className="loss">{selected.stop_loss}</strong>
              </div>
              <div>
                <span>اهداف</span>
                <strong className="gain">
                  {selected.targets.map((x: Json) => x.price).join(" / ")}
                </strong>
              </div>
            </div>
            <h3>تحلیل تکنیکال</h3>
            <p>{selected.technical_analysis || "تحلیلی ثبت نشده است."}</p>
            <h3>تحلیل فاندامنتال</h3>
            <p>{selected.fundamental_analysis || "تحلیلی ثبت نشده است."}</p>
            <div className="status-actions">
              <span>تغییر وضعیت:</span>
              {["PENDING", "ACTIVE", "CLOSED", "CANCELED"].map((s) => (
                <button
                  key={s}
                  className="ghost"
                  disabled={selected.status === s}
                  onClick={() => changeStatus(selected.id, s)}
                >
                  {statusFa[s]}
                </button>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

function ExpertsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null),
    [selected, setSelected] = useState<Json | null>(null),
    [logs, setLogs] = useState<Json | null>(null);
  const load = () =>
    request("/experts")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function open(x: Json) {
    setSelected(x);
    setLogs(null);
    setLogs(await request(`/experts/${x.account_number}/logs`));
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selected) return;
    const f = Object.fromEntries(new FormData(e.currentTarget));
    const body = {
      risk_percent: +f.risk_percent,
      max_daily_loss: +f.max_daily_loss,
      max_open_trades: +f.max_open_trades,
      fixed_lot: f.fixed_lot ? +f.fixed_lot : null,
      trading_enabled: f.trading_enabled === "on",
    };
    try {
      await request(`/experts/${selected.account_number}/settings`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      toast("تنظیمات ریسک اکسپرت ذخیره شد");
      setSelected(null);
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="شبکه اجرای خودکار"
        title="مدیریت اکسپرت‌ها"
        subtitle="اتصال MT5، عملکرد، ریسک و رخدادهای هر حساب در یک نمای واحد."
      />
      <div className="expert-grid">
        {data?.items.map((x: Json) => (
          <article className="expert-card" key={x.account_number}>
            <div className="expert-head">
              <div className="bot-icon">
                <Bot />
              </div>
              <div>
                <b>{x.first_name || x.username || "حساب معاملاتی"}</b>
                <span className="mono">#{x.account_number}</span>
              </div>
              <Badge value={x.online ? "ACTIVE" : "BLOCKED"} />
            </div>
            <div className="expert-profit">
              <span>سود ثبت‌شده</span>
              <strong className={x.profit >= 0 ? "gain" : "loss"}>
                ${money.format(x.profit)}
              </strong>
            </div>
            <div className="expert-meta">
              <span>
                <small>بروکر</small>
                {x.broker || "—"}
              </span>
              <span>
                <small>نسخه EA</small>
                {x.ea_version || "—"}
              </span>
              <span>
                <small>معاملات باز</small>
                {fa.format(x.open_trades)}
              </span>
              <span>
                <small>ریسک</small>
                {x.risk_percent}٪
              </span>
            </div>
            <footer>
              <span>آخرین اتصال: {date(x.last_seen_at)}</span>
              <button className="table-action" onClick={() => open(x)}>
                تنظیمات <Settings2 />
              </button>
            </footer>
          </article>
        ))}
        {!data && <Loader />}
        {data && !data.items.length && (
          <Empty text="هنوز اکسپرتی متصل نشده است" />
        )}
      </div>
      {selected && (
        <Modal
          title={`تنظیمات اکسپرت #${selected.account_number}`}
          onClose={() => setSelected(null)}
          wide
        >
          <form className="form-grid" onSubmit={save}>
            <Field label="ریسک هر معامله (%)">
              <input
                name="risk_percent"
                type="number"
                step=".1"
                defaultValue={selected.risk_percent}
              />
            </Field>
            <Field label="حد زیان روزانه (%)">
              <input
                name="max_daily_loss"
                type="number"
                step=".1"
                defaultValue={selected.max_daily_loss}
              />
            </Field>
            <Field label="حداکثر معاملات باز">
              <input
                name="max_open_trades"
                type="number"
                defaultValue={selected.max_open_trades}
              />
            </Field>
            <Field label="لات ثابت (اختیاری)">
              <input
                name="fixed_lot"
                type="number"
                step=".01"
                defaultValue={selected.fixed_lot || ""}
              />
            </Field>
            <Field label="اجازه معامله">
              <label className="switch">
                <input
                  name="trading_enabled"
                  type="checkbox"
                  defaultChecked={!!selected.trading_enabled}
                />
                <i />
              </label>
            </Field>
            <div className="modal-section full">
              <h3>آخرین لاگ‌های اجرایی</h3>
              {logs ? (
                <div className="log-list">
                  {logs.events.slice(0, 8).map((e: Json) => (
                    <div key={e.id}>
                      <code>{e.event_name}</code>
                      <span>
                        {e.symbol} • #{e.ticket}
                      </span>
                      <b className={e.profit >= 0 ? "gain" : "loss"}>
                        {e.profit}
                      </b>
                      <small>{date(e.event_time)}</small>
                    </div>
                  ))}
                  {!logs.events.length && <Empty />}
                </div>
              ) : (
                <Loader />
              )}
            </div>
            <div className="form-actions full">
              <button
                type="button"
                className="ghost"
                onClick={() => setSelected(null)}
              >
                انصراف
              </button>
              <button className="primary">ذخیره سیاست ریسک</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function ReportsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [period, setPeriod] = useState("30d"),
    [data, setData] = useState<Json | null>(null);
  useEffect(() => {
    request(`/reports?period=${period}`)
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  }, [period]);
  async function download(kind: string) {
    const token = localStorage.getItem("nexus-admin-token");
    const r = await fetch(`${API}/reports/export.${kind}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) return toast("خروجی گزارش ناموفق بود", "error");
    const blob = await r.blob(),
      url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = `nexus-report.${kind}`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHead
        eyebrow="هوش معاملاتی"
        title="گزارش‌ها و آمار"
        subtitle="تحلیل سودآوری، نرخ برد و عملکرد نمادها بر پایه داده‌های قطعی اجرا."
        action={
          <div className="head-actions">
            <button className="ghost" onClick={() => download("xlsx")}>
              <Download /> Excel
            </button>
            <button className="ghost" onClick={() => download("pdf")}>
              <Download /> PDF
            </button>
          </div>
        }
      />
      <div className="period-tabs">
        {[
          ["7d", "۷ روز"],
          ["30d", "۳۰ روز"],
          ["90d", "۹۰ روز"],
          ["all", "کل دوره"],
        ].map((x) => (
          <button
            key={x[0]}
            className={period === x[0] ? "active" : ""}
            onClick={() => setPeriod(x[0])}
          >
            {x[1]}
          </button>
        ))}
      </div>
      {data ? (
        <>
          <section className="report-summary">
            <div>
              <span>سود خالص</span>
              <strong>${money.format(data.summary.net_profit)}</strong>
            </div>
            <div>
              <span>تعداد معاملات</span>
              <strong>{fa.format(data.summary.trades)}</strong>
            </div>
            <div>
              <span>نرخ برد</span>
              <strong>{fa.format(data.summary.win_rate)}٪</strong>
            </div>
            <div>
              <span>میانگین سود</span>
              <strong>${money.format(data.summary.avg_profit)}</strong>
            </div>
          </section>
          <section className="report-grid">
            <article className="panel">
              <div className="panel-head">
                <div>
                  <small>جریان بازده</small>
                  <h2>سود روزانه</h2>
                </div>
              </div>
              <div className="chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.daily}>
                    <CartesianGrid stroke="#172a3f" vertical={false} />
                    <XAxis dataKey="date" stroke="#668099" />
                    <YAxis stroke="#668099" />
                    <Tooltip
                      contentStyle={{
                        background: "#0b1828",
                        border: "1px solid #1b334a",
                      }}
                    />
                    <Bar
                      dataKey="profit"
                      fill="#13d9a3"
                      radius={[5, 5, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>
            <article className="panel symbol-table">
              <div className="panel-head">
                <div>
                  <small>تفکیک دارایی</small>
                  <h2>عملکرد نمادها</h2>
                </div>
              </div>
              {data.by_symbol.map((x: Json) => (
                <div className="symbol-row" key={x.symbol}>
                  <b>{x.symbol}</b>
                  <span>{fa.format(x.trades)} معامله</span>
                  <span>{fa.format(x.win_rate)}٪ برد</span>
                  <strong className={x.profit >= 0 ? "gain" : "loss"}>
                    ${money.format(x.profit)}
                  </strong>
                </div>
              ))}
              {!data.by_symbol.length && <Empty />}
            </article>
          </section>
        </>
      ) : (
        <Loader />
      )}
    </>
  );
}

function NotificationsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      channels = f.getAll("channels");
    try {
      await request("/notifications", {
        method: "POST",
        body: JSON.stringify({
          channels,
          audience: f.get("audience"),
          message: f.get("message"),
        }),
      });
      toast("پیام در صف ارسال قرار گرفت");
      e.currentTarget.reset();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="ارتباط یکپارچه"
        title="مرکز اطلاع‌رسانی"
        subtitle="یک پیام، چند کانال؛ ارسال هدفمند به اعضای موردنظر."
      />
      <section className="notify-layout">
        <form className="panel notify-form" onSubmit={submit}>
          <div className="panel-head">
            <div>
              <small>پیام جدید</small>
              <h2>ساخت اعلان</h2>
            </div>
            <Send />
          </div>
          <Field label="مخاطبان">
            <select name="audience">
              <option value="ALL">همه کاربران</option>
              <option value="VIP">فقط اعضای VIP</option>
              <option value="REGULAR">کاربران عادی</option>
            </select>
          </Field>
          <Field label="متن پیام">
            <textarea
              name="message"
              rows={8}
              placeholder="پیام خود را بنویسید…"
              required
            />
          </Field>
          <div className="channel-checks">
            <label>
              <input
                type="checkbox"
                name="channels"
                value="TELEGRAM"
                defaultChecked
              />
              <span>
                <Send />
                Telegram
              </span>
            </label>
            <label>
              <input type="checkbox" name="channels" value="EMAIL" />
              <span>
                <Bell />
                Email
              </span>
            </label>
            <label>
              <input type="checkbox" name="channels" value="PUSH" />
              <span>
                <Zap />
                Push
              </span>
            </label>
          </div>
          <button className="primary">
            <Send /> قرار دادن در صف ارسال
          </button>
        </form>
        <article className="panel delivery-info">
          <div className="signal-wave">
            <span />
            <span />
            <span />
            <Bell />
          </div>
          <h2>ارسال کنترل‌شده</h2>
          <p>
            پیام‌های تلگرام از مسیر فعلی ربات پردازش می‌شوند. کانال‌های ایمیل و
            Push پس از تنظیم سرویس‌دهنده، از همین صف آماده تحویل خواهند بود.
          </p>
          <div className="security-note">
            <ShieldCheck />
            <span>
              <b>امنیت مخاطبان</b>اطلاعات کاربران هرگز به مرورگر منتقل نمی‌شود.
            </span>
          </div>
        </article>
      </section>
    </>
  );
}

function AuditPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null);
  useEffect(() => {
    request("/audit")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  }, []);
  return (
    <>
      <PageHead
        eyebrow="ردپای تغییرات"
        title="رویدادهای امنیتی"
        subtitle="ثبت تغییرناپذیر اقدامات مدیریتی و رخدادهای حساس سامانه."
      />
      <section className="table-panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>زمان</th>
                <th>شناسه مدیر</th>
                <th>عملیات</th>
                <th>هدف</th>
                <th>جزئیات</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((a: Json) => (
                <tr key={a.id}>
                  <td>{date(a.created_at)}</td>
                  <td className="mono">#{a.admin_id}</td>
                  <td>
                    <code className="action-code">{a.action}</code>
                  </td>
                  <td>{a.target_id || "—"}</td>
                  <td className="muted">{a.details || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data && <Loader />}
        </div>
      </section>
    </>
  );
}

function OperationsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null);
  const load = () =>
    request("/operations")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function control(key: string, enabled: boolean) {
    try {
      await request(`/operations/controls/${key}`, {
        method: "PUT",
        body: JSON.stringify({
          enabled,
          scope: "GLOBAL",
          reason: "تغییر از مرکز عملیات وب",
        }),
      });
      toast(enabled ? "کنترل حفاظتی فعال شد" : "کنترل حفاظتی غیرفعال شد");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  if (!data) return <Loader />;
  const killed = !!data.controls.KILL_SWITCH?.enabled;
  return (
    <>
      <PageHead
        eyebrow="فرماندهی بلادرنگ"
        title="مرکز عملیات زنده"
        subtitle="موقعیت‌ها، اتصال اکسپرت‌ها، دستورات و خطاهای اجرایی در یک نمای واحد."
        action={
          <button
            className={killed ? "primary" : "danger-button"}
            onClick={() => control("KILL_SWITCH", !killed)}
          >
            <Power />
            {killed ? "فعال‌سازی معاملات" : "توقف اضطراری کل سیستم"}
          </button>
        }
      />
      <section className="ops-health">
        {Object.entries(data.health).map(([k, v]) => (
          <div key={k}>
            <span className={v ? "pulse" : "pulse off"} />
            <b>{k.toUpperCase()}</b>
            <small>{v ? "عملیاتی" : "نیازمند بررسی"}</small>
          </div>
        ))}
      </section>
      <section className="ops-grid">
        <article className="panel ops-live">
          <div className="panel-head">
            <div>
              <small>Broker Truth</small>
              <h2>موقعیت‌ها و سفارش‌های زنده</h2>
            </div>
            <Badge value={killed ? "BLOCKED" : "ACTIVE"} />
          </div>
          {data.live.length ? (
            data.live.map((x: Json) => (
              <div className="live-row" key={`${x.account_number}-${x.ticket}`}>
                <span
                  className={`direction ${["BUY", "LONG"].includes(x.direction) ? "buy" : "sell"}`}
                >
                  {x.direction || x.state_type}
                </span>
                <div>
                  <b>{x.symbol}</b>
                  <small>
                    #{x.ticket} • حساب {x.account_number}
                  </small>
                </div>
                <span>حجم {x.volume}</span>
                <strong className={x.profit >= 0 ? "gain" : "loss"}>
                  ${money.format(x.profit)}
                </strong>
                <button className="table-action">
                  کنترل <Wrench />
                </button>
              </div>
            ))
          ) : (
            <Empty text="موقعیت بازی در بروکر گزارش نشده است" />
          )}
        </article>
        <article className="panel">
          <div className="panel-head">
            <div>
              <small>Heartbeat</small>
              <h2>اتصالات MT5</h2>
            </div>
          </div>
          {data.heartbeats.slice(0, 8).map((h: Json) => (
            <div className="health-row" key={h.account_number}>
              <span>
                #{h.account_number} • {h.ea_version || "EA"}
              </span>
              <b>
                <i />
                {date(h.last_seen_at)}
              </b>
            </div>
          ))}
          {!data.heartbeats.length && <Empty />}
        </article>
        <article className="panel ops-errors">
          <div className="panel-head">
            <div>
              <small>Recovery Queue</small>
              <h2>خطاها و ارسال‌های ناموفق</h2>
            </div>
            <span className="error-count">
              {fa.format(data.failures.length)}
            </span>
          </div>
          {data.failures.slice(0, 8).map((f: Json) => (
            <div className="failure-row" key={f.id}>
              <Activity />
              <div>
                <b>
                  {f.code || f.signal_id} • {f.symbol}
                </b>
                <small>{f.error_text || f.status}</small>
              </div>
              <button className="ghost">تلاش مجدد</button>
            </div>
          ))}
          {!data.failures.length && <Empty text="خطای بازی وجود ندارد" />}
        </article>
        <article className="panel command-log">
          <div className="panel-head">
            <div>
              <small>Audit Trail</small>
              <h2>آخرین دستورات معاملاتی</h2>
            </div>
          </div>
          {data.commands.slice(0, 8).map((c: Json) => (
            <div key={c.id}>
              <code>#{c.id}</code>
              <span>{c.command}</span>
              <b>Signal #{c.signal_id}</b>
              <small>{date(c.created_at)}</small>
            </div>
          ))}
        </article>
      </section>
    </>
  );
}

function RiskCenterPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null),
    [create, setCreate] = useState(false);
  const load = () =>
    request("/risk-center")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await request("/risk-center/policies", {
        method: "POST",
        body: JSON.stringify({
          name: f.name,
          risk_percent: +f.risk_percent,
          max_daily_loss: +f.max_daily_loss,
          max_open_trades: +f.max_open_trades,
          max_daily_trades: +f.max_daily_trades,
          symbols: String(f.symbols || "")
            .split(",")
            .filter(Boolean),
        }),
      });
      toast("پروفایل ریسک ساخته شد");
      setCreate(false);
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="حفاظت سرمایه"
        title="مرکز سیاست‌های ریسک"
        subtitle="کنترل انتخاب کاربران، پروفایل‌های استاندارد و هشدارهای زیان."
        action={
          <button className="primary" onClick={() => setCreate(true)}>
            <Plus />
            پروفایل ریسک
          </button>
        }
      />
      {data ? (
        <>
          <section className="risk-overview">
            <div>
              <ShieldCheck />
              <span>
                مدیریت توسط کاربر
                <strong>
                  {fa.format(
                    data.preferences.filter(
                      (x: Json) => x.management_mode === "SELF",
                    ).length,
                  )}
                </strong>
              </span>
            </div>
            <div>
              <CircleUserRound />
              <span>
                واگذار به ادمین
                <strong>
                  {fa.format(
                    data.preferences.filter(
                      (x: Json) => x.management_mode === "ADMIN",
                    ).length,
                  )}
                </strong>
              </span>
            </div>
            <div>
              <Activity />
              <span>
                هشدار زیان هفتگی
                <strong>{fa.format(data.breaches.length)}</strong>
              </span>
            </div>
          </section>
          <section className="table-panel">
            <div className="table-meta">
              <span>تنظیمات کاربران</span>
              <small>آخرین تغییرات مدیریت سرمایه</small>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>کاربر</th>
                    <th>حالت مدیریت</th>
                    <th>ریسک</th>
                    <th>زیان روزانه</th>
                    <th>معاملات باز</th>
                    <th>توقف اضطراری</th>
                    <th>بروزرسانی</th>
                  </tr>
                </thead>
                <tbody>
                  {data.preferences.map((x: Json) => (
                    <tr key={x.telegram_id}>
                      <td>{x.first_name || x.username || x.telegram_id}</td>
                      <td>
                        <Badge
                          value={
                            x.management_mode === "SELF"
                              ? "ACTIVE"
                              : "MODERATOR"
                          }
                        />
                      </td>
                      <td>{x.risk_percent}٪</td>
                      <td>{x.max_daily_loss}٪</td>
                      <td>{x.max_open_trades}</td>
                      <td>{x.emergency_stop ? "فعال" : "خاموش"}</td>
                      <td>{date(x.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <Loader />
      )}
      {create && (
        <Modal title="ساخت پروفایل ریسک" onClose={() => setCreate(false)}>
          <form className="form-grid" onSubmit={save}>
            <Field label="نام پروفایل" full>
              <input name="name" required placeholder="متعادل" />
            </Field>
            <Field label="ریسک هر معامله">
              <input
                name="risk_percent"
                type="number"
                step=".1"
                defaultValue="1"
              />
            </Field>
            <Field label="زیان روزانه">
              <input name="max_daily_loss" type="number" defaultValue="3" />
            </Field>
            <Field label="معاملات باز">
              <input name="max_open_trades" type="number" defaultValue="3" />
            </Field>
            <Field label="معاملات روزانه">
              <input name="max_daily_trades" type="number" defaultValue="10" />
            </Field>
            <Field label="نمادهای مجاز" full>
              <input name="symbols" placeholder="XAUUSD,BTCUSDT" />
            </Field>
            <button className="primary full">ذخیره پروفایل</button>
          </form>
        </Modal>
      )}
    </>
  );
}

function CommercePage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null);
  const load = () =>
    request("/commerce")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function action(id: number, a: string) {
    try {
      await request(`/commerce/licenses/${id}/action`, {
        method: "POST",
        body: JSON.stringify({ action: a, days: 30 }),
      });
      toast("وضعیت لایسنس تغییر کرد");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  if (!data) return <Loader />;
  return (
    <>
      <PageHead
        eyebrow="درآمد و دسترسی"
        title="مالی و اشتراک"
        subtitle="پرداخت‌ها، پلن‌ها، لایسنس‌ها، تخفیف‌ها و شاخص‌های درآمد."
      />
      <section className="report-summary">
        <div>
          <span>درآمد امروز</span>
          <strong>${money.format(data.summary.revenue_today_usdt)}</strong>
        </div>
        <div>
          <span>درآمد ماه</span>
          <strong>${money.format(data.summary.revenue_month_usdt)}</strong>
        </div>
        <div>
          <span>اشتراک فعال</span>
          <strong>{fa.format(data.summary.active)}</strong>
        </div>
        <div>
          <span>پرداخت منتظر</span>
          <strong>{fa.format(data.summary.pending)}</strong>
        </div>
      </section>
      <section className="commerce-grid">
        <article className="table-panel">
          <div className="table-meta">
            <span>لایسنس‌های اخیر</span>
            <small>{fa.format(data.licenses.length)} رکورد</small>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>کاربر</th>
                  <th>پلن</th>
                  <th>وضعیت</th>
                  <th>انقضا</th>
                  <th>عملیات</th>
                </tr>
              </thead>
              <tbody>
                {data.licenses.map((x: Json) => (
                  <tr key={x.id}>
                    <td>{x.first_name || x.username || x.telegram_id}</td>
                    <td>{x.plan_code}</td>
                    <td>
                      <Badge
                        value={
                          x.status.toUpperCase() === "ACTIVE"
                            ? "ACTIVE"
                            : "BLOCKED"
                        }
                      />
                    </td>
                    <td>{date(x.expires_at)}</td>
                    <td>
                      <div className="inline-actions">
                        <button onClick={() => action(x.id, "EXTEND")}>
                          +۳۰ روز
                        </button>
                        <button
                          onClick={() =>
                            action(
                              x.id,
                              x.status === "active" ? "SUSPEND" : "ACTIVATE",
                            )
                          }
                        >
                          {x.status === "active" ? "تعلیق" : "فعال‌سازی"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <article className="panel plans-panel">
          <div className="panel-head">
            <div>
              <small>Catalog</small>
              <h2>پلن‌های فروش</h2>
            </div>
          </div>
          {data.plans.map((p: Json) => (
            <div className="plan-row" key={p.code}>
              <div>
                <b>{p.title_fa}</b>
                <small>
                  {p.code} • {p.days} روز
                </small>
              </div>
              <strong>${p.usdt_price}</strong>
              <Badge value={p.active ? "ACTIVE" : "BLOCKED"} />
            </div>
          ))}
        </article>
      </section>
    </>
  );
}

function CommunicationsPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null),
    [create, setCreate] = useState(false);
  const load = () =>
    request("/communications")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await request("/communications/templates", {
        method: "POST",
        body: JSON.stringify(f),
      });
      toast("قالب پیام ذخیره شد");
      setCreate(false);
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  return (
    <>
      <PageHead
        eyebrow="تجربه مشتری"
        title="پشتیبانی و پیام‌ها"
        subtitle="تیکت‌ها، قالب‌های پیام، کمپین‌ها و وضعیت تحویل اعلان‌ها."
        action={
          <button className="primary" onClick={() => setCreate(true)}>
            <Plus />
            قالب پیام
          </button>
        }
      />
      {data ? (
        <section className="comms-grid">
          <article className="panel">
            <div className="panel-head">
              <div>
                <small>Support Inbox</small>
                <h2>صندوق پشتیبانی</h2>
              </div>
              <span>{fa.format(data.tickets.length)}</span>
            </div>
            {data.tickets.map((t: Json) => (
              <div className="ticket-row" key={t.id}>
                <span className={t.priority === "URGENT" ? "urgent" : ""}>
                  {t.priority}
                </span>
                <div>
                  <b>{t.subject}</b>
                  <small>{t.first_name || t.username || t.telegram_id}</small>
                </div>
                <Badge value={t.status === "OPEN" ? "ACTIVE" : "CLOSED"} />
              </div>
            ))}
            {!data.tickets.length && <Empty text="تیکت بازی وجود ندارد" />}
          </article>
          <article className="panel">
            <div className="panel-head">
              <div>
                <small>Delivery</small>
                <h2>آخرین ارسال‌ها</h2>
              </div>
            </div>
            {data.jobs.slice(0, 10).map((j: Json) => (
              <div className="job-row" key={j.id}>
                <div>
                  <b>{j.channels}</b>
                  <small>
                    {j.audience} • {date(j.created_at)}
                  </small>
                </div>
                <span>{fa.format(j.sent_count)} موفق</span>
                <Badge
                  value={
                    j.status === "SENT"
                      ? "ACTIVE"
                      : j.status === "QUEUED"
                        ? "PENDING"
                        : "MODERATOR"
                  }
                />
              </div>
            ))}
          </article>
          <article className="panel templates-panel">
            <div className="panel-head">
              <div>
                <small>Content Library</small>
                <h2>قالب‌های آماده</h2>
              </div>
            </div>
            {data.templates.map((t: Json) => (
              <div className="template-row" key={t.id}>
                <div>
                  <b>{t.name}</b>
                  <small>{t.channel}</small>
                </div>
                <p>{t.body}</p>
              </div>
            ))}
            {!data.templates.length && <Empty />}
          </article>
        </section>
      ) : (
        <Loader />
      )}
      {create && (
        <Modal title="قالب پیام جدید" onClose={() => setCreate(false)}>
          <form className="form-grid" onSubmit={save}>
            <Field label="نام" full>
              <input name="name" required />
            </Field>
            <Field label="کانال" full>
              <select name="channel">
                <option>TELEGRAM</option>
                <option>EMAIL</option>
                <option>PUSH</option>
              </select>
            </Field>
            <Field label="متن قالب" full>
              <textarea name="body" rows={7} required />
            </Field>
            <button className="primary full">ذخیره قالب</button>
          </form>
        </Modal>
      )}
    </>
  );
}

function SecurityCenterPage({
  toast,
}: {
  toast: (m: string, k?: "ok" | "error") => void;
}) {
  const [data, setData] = useState<Json | null>(null);
  const load = () =>
    request("/security-center")
      .then(setData)
      .catch((e) => toast(e.message, "error"));
  useEffect(() => {
    load();
  }, []);
  async function backup() {
    try {
      await request("/security-center/backups", { method: "POST" });
      toast("نسخه پشتیبان امن ساخته شد");
      load();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }
  if (!data) return <Loader />;
  return (
    <>
      <PageHead
        eyebrow="دفاع و تداوم سرویس"
        title="امنیت و سلامت سیستم"
        subtitle="مدیران، نشست‌ها، پیکربندی امنیتی، Audit و نسخه‌های پشتیبان."
        action={
          <button className="primary" onClick={backup}>
            <Download />
            پشتیبان‌گیری اکنون
          </button>
        }
      />
      <section className="security-checks">
        {Object.entries(data.checks).map(([k, v]) => (
          <div className={v ? "pass" : "warn"} key={k}>
            <ShieldCheck />
            <span>
              <b>{k.replaceAll("_", " ")}</b>
              <small>{v ? "تأیید شده" : "نیازمند اقدام"}</small>
            </span>
          </div>
        ))}
      </section>
      <section className="security-grid">
        <article className="panel">
          <div className="panel-head">
            <div>
              <small>Access Control</small>
              <h2>مدیران سیستم</h2>
            </div>
          </div>
          {data.admins.map((a: Json) => (
            <div className="admin-row" key={a.id}>
              <CircleUserRound />
              <div>
                <b>{a.display_name}</b>
                <small>
                  @{a.username} • {date(a.last_login_at)}
                </small>
              </div>
              <Badge value={a.active ? "ADMIN" : "BLOCKED"} />
            </div>
          ))}
        </article>
        <article className="panel">
          <div className="panel-head">
            <div>
              <small>Disaster Recovery</small>
              <h2>نسخه‌های پشتیبان</h2>
            </div>
          </div>
          {data.backups.map((b: Json) => (
            <div className="backup-row" key={b.name}>
              <ServerCog />
              <div>
                <b>{b.name}</b>
                <small>
                  {money.format(b.size / 1024 / 1024)} MB • {date(b.created_at)}
                </small>
              </div>
              <ShieldCheck />
            </div>
          ))}
          {!data.backups.length && (
            <Empty text="هنوز نسخه پشتیبانی ایجاد نشده است" />
          )}
        </article>
        <article className="panel security-audit">
          <div className="panel-head">
            <div>
              <small>Security Audit</small>
              <h2>رویدادهای حساس</h2>
            </div>
          </div>
          {data.audits.slice(0, 12).map((a: Json) => (
            <div key={a.id}>
              <code>{a.action}</code>
              <span>{a.details || "—"}</span>
              <small>{date(a.created_at)}</small>
            </div>
          ))}
        </article>
      </section>
    </>
  );
}

function UserPortal() {
  const [data, setData] = useState<Json | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [riskMode, setRiskMode] = useState<"SELF" | "ADMIN">("SELF");
  const [riskSaved, setRiskSaved] = useState("");
  const token = localStorage.getItem("nexus-user-token");
  const load = useCallback(
    () =>
      portalRequest("/overview")
        .then(setData)
        .catch((e) => {
          localStorage.removeItem("nexus-user-token");
          setError(e.message);
        }),
    [],
  );
  useEffect(() => {
    if (token) load();
  }, [token]);
  useEffect(() => {
    if (data?.risk?.management_mode) setRiskMode(data.risk.management_mode);
  }, [data?.risk?.management_mode]);

  async function login(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      const result = await portalRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          telegram_id: Number(f.get("telegram_id")),
          license_key: f.get("license_key"),
        }),
      });
      localStorage.setItem("nexus-user-token", result.token);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function saveRisk(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!data) return;
    setRiskSaved("");
    const f = new FormData(e.currentTarget);
    const current = data.risk;
    try {
      await portalRequest("/risk-settings", {
        method: "PUT",
        body: JSON.stringify({
          management_mode: riskMode,
          risk_percent: Number(f.get("risk_percent") || current.risk_percent),
          max_daily_loss: Number(
            f.get("max_daily_loss") || current.max_daily_loss,
          ),
          max_open_trades: Number(
            f.get("max_open_trades") || current.max_open_trades,
          ),
          max_daily_trades: Number(
            f.get("max_daily_trades") || current.max_daily_trades,
          ),
          fixed_lot: f.get("fixed_lot") ? Number(f.get("fixed_lot")) : null,
          emergency_stop: f.get("emergency_stop") === "on",
        }),
      });
      setRiskSaved(
        riskMode === "SELF"
          ? "تنظیمات شخصی ذخیره و فعال شد."
          : "مدیریت ریسک به ادمین واگذار شد.",
      );
      await load();
    } catch (e) {
      setRiskSaved((e as Error).message);
    }
  }

  if (!token || !data)
    return (
      <main className="portal-login">
        <section className="portal-login-card">
          <div className="portal-logo">
            <Zap />
            <b>NEXUS</b>
            <span>TRADER PORTAL</span>
          </div>
          <h1>پنل معامله‌گر</h1>
          <p>اشتراک، سیگنال‌ها و عملکرد اکسپرت خود را یک‌جا دنبال کنید.</p>
          <form onSubmit={login}>
            <Field label="شناسه تلگرام">
              <input
                name="telegram_id"
                type="number"
                inputMode="numeric"
                required
                autoFocus
              />
            </Field>
            <Field label="کلید لایسنس">
              <input
                name="license_key"
                dir="ltr"
                placeholder="NXS-••••••••••••"
                required
              />
            </Field>
            {error && <div className="form-error">{error}</div>}
            <button className="primary" disabled={loading}>
              {loading ? "در حال ورود…" : "ورود به حساب"}
              <ChevronLeft />
            </button>
          </form>
          <button
            className="portal-link"
            onClick={() => (location.href = "/admin/")}
          >
            <ShieldCheck /> ورود مدیر سیستم
          </button>
        </section>
      </main>
    );

  const ent = data.entitlements,
    account = data.account;
  return (
    <div className="user-portal">
      <header className="portal-top">
        <div className="portal-logo">
          <Zap />
          <b>NEXUS</b>
          <span>TRADER</span>
        </div>
        <nav>
          <a className="active">داشبورد</a>
          <a href="#signals">سیگنال‌ها</a>
          <a href="#trades">معاملات من</a>
          <a href="#risk">مدیریت ریسک</a>
          <a href="#expert">اکسپرت</a>
        </nav>
        <div className="portal-user">
          <div>
            <b>{data.user.first_name || data.user.username || "کاربر NEXUS"}</b>
            <small>@{data.user.username || data.user.telegram_id}</small>
          </div>
          <span>{(data.user.first_name || "N")[0]}</span>
          <button
            className="icon-btn"
            onClick={() => {
              localStorage.removeItem("nexus-user-token");
              setData(null);
            }}
          >
            <LogOut />
          </button>
        </div>
      </header>
      <main className="portal-content">
        <section className="portal-welcome">
          <div>
            <small>مرکز معاملات شخصی</small>
            <h1>سلام {data.user.first_name || "معامله‌گر"} 👋</h1>
            <p>وضعیت امروز حساب و آخرین فرصت‌های معاملاتی شما آماده است.</p>
          </div>
          <span className="market-open">
            <i /> بازار در دسترس
          </span>
        </section>
        <section className="portal-kpis">
          <article>
            <div className="cyan">
              <WalletCards />
            </div>
            <span>سود خالص ۳۰ روز</span>
            <strong className={data.stats.net_pnl >= 0 ? "gain" : "loss"}>
              ${money.format(data.stats.net_pnl)}
            </strong>
            <small>{fa.format(data.stats.closed)} معامله بسته‌شده</small>
          </article>
          <article>
            <div className="violet">
              <TrendingUp />
            </div>
            <span>نرخ موفقیت</span>
            <strong>
              {data.stats.closed
                ? fa.format(
                    Math.round((data.stats.wins * 100) / data.stats.closed),
                  )
                : "۰"}
              ٪
            </strong>
            <small>
              {fa.format(data.stats.wins)} برد / {fa.format(data.stats.losses)}{" "}
              باخت
            </small>
          </article>
          <article>
            <div className="green">
              <Bot />
            </div>
            <span>اتصال اکسپرت</span>
            <strong>{account ? "متصل" : "متصل نیست"}</strong>
            <small>
              {account
                ? `${account.broker || "MT5"} • #${account.account_number}`
                : "از ربات راه‌اندازی کنید"}
            </small>
          </article>
          <article>
            <div className="orange">
              <ShieldCheck />
            </div>
            <span>اشتراک</span>
            <strong>{ent.active ? ent.plan_code || "فعال" : "غیرفعال"}</strong>
            <small>
              {ent.vip_expires_at
                ? `تا ${date(ent.vip_expires_at)}`
                : "بدون VIP"}
            </small>
          </article>
        </section>
        <section className="portal-grid">
          <article className="panel portal-signals" id="signals">
            <div className="panel-head">
              <div>
                <small>فرصت‌های فعال</small>
                <h2>آخرین سیگنال‌ها</h2>
              </div>
              <span className="live-chip">
                <i /> زنده
              </span>
            </div>
            {data.signals.length ? (
              data.signals.slice(0, 6).map((s: Json) => (
                <div className="portal-signal" key={s.id}>
                  <span
                    className={`direction ${["BUY", "LONG"].includes(s.direction) ? "buy" : "sell"}`}
                  >
                    {s.direction}
                  </span>
                  <div>
                    <b>{s.symbol}</b>
                    <small>
                      {s.code} • {s.timeframe}
                    </small>
                  </div>
                  <div>
                    <small>ورود</small>
                    <b>{s.entry_price}</b>
                  </div>
                  <div>
                    <small>حد سود</small>
                    <b className="gain">{s.tp1}</b>
                  </div>
                  <div>
                    <small>حد ضرر</small>
                    <b className="loss">{s.stop_loss}</b>
                  </div>
                  <Badge value={s.status} />
                </div>
              ))
            ) : (
              <Empty text="در حال حاضر سیگنال فعالی وجود ندارد" />
            )}
          </article>
          <article className="panel subscription-card">
            <div className="subscription-glow" />
            <small>سطح دسترسی</small>
            <h2>{ent.vip ? "NEXUS VIP" : "NEXUS FREE"}</h2>
            <p>
              {ent.vip
                ? "تمام سیگنال‌های عمومی و VIP برای شما فعال است."
                : "به سیگنال‌های عمومی دسترسی دارید؛ با ارتقا، فرصت‌های VIP هم باز می‌شوند."}
            </p>
            <div className="entitlement">
              <ShieldCheck /> سیگنال VIP <b>{ent.vip ? "فعال" : "غیرفعال"}</b>
            </div>
            <div className="entitlement">
              <Bot /> AutoTrade <b>{ent.autotrade ? "فعال" : "غیرفعال"}</b>
            </div>
            <button className="primary">مدیریت اشتراک</button>
          </article>
          <article className="panel portal-trades" id="trades">
            <div className="panel-head">
              <div>
                <small>تاریخچه اجرا</small>
                <h2>معاملات اخیر من</h2>
              </div>
            </div>
            {data.trades.length ? (
              data.trades.slice(0, 8).map((t: Json) => (
                <div
                  className="trade-row"
                  key={`${t.ticket}-${t.first_seen_at}`}
                >
                  <div>
                    <b>{t.symbol}</b>
                    <small>
                      #{t.ticket} • {t.direction}
                    </small>
                  </div>
                  <Badge value={t.status || t.signal_status || "ACTIVE"} />
                  <span>{date(t.first_seen_at)}</span>
                  <strong
                    className={(t.result_value || 0) >= 0 ? "gain" : "loss"}
                  >
                    {t.result_value == null
                      ? "باز"
                      : `$${money.format(t.result_value)}`}
                  </strong>
                </div>
              ))
            ) : (
              <Empty text="هنوز معامله‌ای ثبت نشده است" />
            )}
          </article>
          <article className="panel risk-manager" id="risk">
            <div className="panel-head">
              <div>
                <small>کنترل سرمایه</small>
                <h2>مدیریت ریسک من</h2>
              </div>
              <SlidersHorizontal />
            </div>
            <div className="risk-mode">
              <button
                className={riskMode === "SELF" ? "active" : ""}
                onClick={() => setRiskMode("SELF")}
              >
                <CircleUserRound />
                <b>تنظیم توسط من</b>
                <small>کنترل کامل پارامترها</small>
              </button>
              <button
                className={riskMode === "ADMIN" ? "active" : ""}
                onClick={() => setRiskMode("ADMIN")}
              >
                <ShieldCheck />
                <b>واگذاری به ادمین</b>
                <small>مدیریت حرفه‌ای مرکزی</small>
              </button>
            </div>
            <form
              className={
                riskMode === "ADMIN" ? "risk-form locked" : "risk-form"
              }
              onSubmit={saveRisk}
            >
              <Field label="ریسک هر معامله (%)">
                <input
                  name="risk_percent"
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="10"
                  defaultValue={data.risk.risk_percent}
                  readOnly={riskMode === "ADMIN"}
                />
              </Field>
              <Field label="حداکثر زیان روزانه (%)">
                <input
                  name="max_daily_loss"
                  type="number"
                  step="0.5"
                  min="0.5"
                  max="25"
                  defaultValue={data.risk.max_daily_loss}
                  readOnly={riskMode === "ADMIN"}
                />
              </Field>
              <Field label="حداکثر معاملات باز">
                <input
                  name="max_open_trades"
                  type="number"
                  min="1"
                  max="20"
                  defaultValue={data.risk.max_open_trades}
                  readOnly={riskMode === "ADMIN"}
                />
              </Field>
              <Field label="حداکثر معاملات روزانه">
                <input
                  name="max_daily_trades"
                  type="number"
                  min="1"
                  max="100"
                  defaultValue={data.risk.max_daily_trades}
                  readOnly={riskMode === "ADMIN"}
                />
              </Field>
              <Field label="حجم ثابت (اختیاری)">
                <input
                  name="fixed_lot"
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="100"
                  placeholder="محاسبه بر اساس ریسک"
                  defaultValue={data.risk.fixed_lot || ""}
                  readOnly={riskMode === "ADMIN"}
                />
              </Field>
              <label className="emergency">
                <span>
                  <b>توقف اضطراری معاملات</b>
                  <small>از باز شدن معامله جدید جلوگیری می‌کند</small>
                </span>
                <span className="switch">
                  <input
                    name="emergency_stop"
                    type="checkbox"
                    defaultChecked={!!data.risk.emergency_stop}
                    disabled={riskMode === "ADMIN"}
                  />
                  <i />
                </span>
              </label>
              {riskMode === "ADMIN" && (
                <div className="risk-lock">
                  <ShieldCheck /> این مقادیر توسط ادمین مدیریت می‌شوند. برای
                  ویرایش، حالت «تنظیم توسط من» را انتخاب کنید.
                </div>
              )}
              {riskSaved && <div className="risk-saved">{riskSaved}</div>}
              <button className="primary">
                {riskMode === "SELF"
                  ? "ذخیره تنظیمات ریسک"
                  : "تأیید واگذاری به ادمین"}
              </button>
            </form>
          </article>
          <article className="panel expert-status" id="expert">
            <div className="panel-head">
              <div>
                <small>اجرای خودکار</small>
                <h2>اکسپرت من</h2>
              </div>
              <Bot />
            </div>
            <div className={`expert-ring ${account ? "online" : ""}`}>
              <Bot />
            </div>
            <h3>{account ? "اکسپرت متصل است" : "اکسپرتی متصل نیست"}</h3>
            <p>
              {account
                ? `آخرین همگام‌سازی: ${date(account.last_seen_at)}`
                : "برای اجرای خودکار سیگنال‌ها، اکسپرت NEXUS را به حساب MT5 متصل کنید."}
            </p>
            {account && (
              <div className="expert-live-count">
                <Activity /> {fa.format(data.live.length)} موقعیت یا سفارش زنده
              </div>
            )}
          </article>
        </section>
      </main>
    </div>
  );
}

export default function App() {
  if (new URLSearchParams(location.search).get("portal") === "user")
    return <UserPortal />;
  const [user, setUser] = useState<Json | null>(null),
    [page, setPage] = useState<Page>("dashboard"),
    [dashboard, setDashboard] = useState<Json | null>(null),
    [live, setLive] = useState(false),
    [toast, setToast] = useState<{ m: string; k: "ok" | "error" } | null>(null);
  const token = localStorage.getItem("nexus-admin-token");
  const notify = (m: string, k: "ok" | "error" = "ok") => {
    setToast({ m, k });
    setTimeout(() => setToast(null), 3500);
  };
  const loadDashboard = useCallback(
    () =>
      request("/dashboard")
        .then(setDashboard)
        .catch((e) => notify(e.message, "error")),
    [],
  );
  useEffect(() => {
    if (token)
      request("/auth/me")
        .then(setUser)
        .catch(() => {});
  }, []);
  useEffect(() => {
    if (user) loadDashboard();
  }, [user]);
  useEffect(() => {
    if (!user || !token) return;
    const protocol = location.protocol === "https:" ? "wss" : "ws",
      ws = new WebSocket(
        `${protocol}://${location.host}${API}/ws?token=${encodeURIComponent(token)}`,
      );
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onmessage = () => {
      if (page === "dashboard") loadDashboard();
    };
    return () => ws.close();
  }, [user, page, token]);
  if (!token || !user) return <Login onLogin={setUser} />;
  const pages: Record<Page, ReactNode> = {
    dashboard: <Dashboard data={dashboard} refresh={loadDashboard} />,
    operations: <OperationsPage toast={notify} />,
    "risk-center": <RiskCenterPage toast={notify} />,
    users: <UsersPage toast={notify} />,
    signals: <SignalsPage toast={notify} />,
    experts: <ExpertsPage toast={notify} />,
    reports: <ReportsPage toast={notify} />,
    commerce: <CommercePage toast={notify} />,
    communications: <CommunicationsPage toast={notify} />,
    notifications: <NotificationsPage toast={notify} />,
    security: <SecurityCenterPage toast={notify} />,
    audit: <AuditPage toast={notify} />,
  };
  return (
    <Shell
      user={user}
      page={page}
      setPage={setPage}
      live={live}
      onLogout={() => {
        localStorage.removeItem("nexus-admin-token");
        setUser(null);
      }}
    >
      {pages[page]}
      {toast && <Toast message={toast.m} kind={toast.k} />}
    </Shell>
  );
}
