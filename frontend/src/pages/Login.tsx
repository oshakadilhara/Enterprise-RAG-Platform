import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Brain,
  Building2,
  Eye,
  EyeOff,
  FileSearch,
  Loader2,
  Lock,
  Mail,
  Shield,
  Sparkles,
  User,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { cn } from "@/lib/utils";

const DEMO_ACCOUNTS = [
  { label: "Org Admin", email: "admin@acme.com", password: "AcmeAdmin123!" },
  { label: "Employee", email: "employee@acme.com", password: "AcmeEmp123!" },
];

const FEATURES = [
  {
    icon: FileSearch,
    title: "Hybrid retrieval",
    desc: "Vector + BM25 search with reranking",
  },
  {
    icon: Shield,
    title: "Enterprise RBAC",
    desc: "Multi-tenant workspaces & audit logs",
  },
  {
    icon: Zap,
    title: "Explainable answers",
    desc: "Citations with confidence scores",
  },
];

function AuthField({
  id,
  label,
  type = "text",
  icon: Icon,
  value,
  onChange,
  placeholder,
  required,
  minLength,
  autoComplete,
}: {
  id: string;
  label: string;
  type?: string;
  icon: React.ElementType;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
}) {
  const [show, setShow] = useState(false);
  const isPassword = type === "password";
  const inputType = isPassword && show ? "text" : type;

  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </Label>
      <div className="group relative">
        <Icon className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground transition-colors group-focus-within:text-primary" />
        <input
          id={id}
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          minLength={minLength}
          autoComplete={autoComplete}
          className={cn(
            "flex h-12 w-full rounded-xl border border-border/80 bg-background/50 pl-11 pr-11 text-sm",
            "placeholder:text-muted-foreground/60 transition-all duration-200",
            "hover:border-primary/30 focus:border-primary focus:bg-background focus:outline-none focus:ring-4 focus:ring-primary/10"
          )}
        />
        {isPassword && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setShow(!show)}
            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
    </div>
  );
}

export function Login() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    organization_name: "",
  });

  const fillDemo = (email: string, password: string) => {
    setForm((f) => ({ ...f, email, password }));
    setError("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data: tokenData } = isRegister
        ? await authApi.register({
            email: form.email,
            password: form.password,
            full_name: form.full_name,
            organization_name: form.organization_name || undefined,
          })
        : await authApi.login(form.email, form.password);

      setTokens(tokenData.access_token, tokenData.refresh_token);
      const { data: user } = await authApi.me();
      setUser(user);
      navigate("/dashboard");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      setError(msg || "Authentication failed. Check your credentials and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* ── Brand panel ─────────────────────────────────────── */}
      <div className="relative hidden w-[52%] overflow-hidden bg-slate-950 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-mesh-gradient opacity-80" />
        <div className="absolute inset-0 bg-grid-pattern bg-grid opacity-40" />

        {/* Floating orbs */}
        <div className="pointer-events-none absolute -left-24 top-1/4 h-72 w-72 animate-pulse-glow rounded-full bg-blue-500/30 blur-[100px]" />
        <div className="pointer-events-none absolute -right-16 bottom-1/4 h-96 w-96 animate-float rounded-full bg-violet-500/25 blur-[120px]" />
        <div className="pointer-events-none absolute left-1/2 top-0 h-64 w-64 -translate-x-1/2 rounded-full bg-cyan-400/20 blur-[80px]" />

        <div className="relative z-10 p-12">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 shadow-lg shadow-blue-500/25">
              <Brain className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-wide text-white/90">Enterprise RAG</p>
              <p className="text-xs text-white/50">Knowledge Intelligence</p>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex flex-1 flex-col justify-center px-12 pb-8">
          <p className="mb-4 inline-flex w-fit items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium text-white/70 backdrop-blur-sm">
            <Sparkles className="h-3.5 w-3.5 text-amber-300" />
            Production-grade retrieval augmented generation
          </p>
          <h1 className="font-display text-5xl leading-[1.1] tracking-tight text-white xl:text-6xl">
            Your company knowledge,
            <span className="block bg-gradient-to-r from-blue-300 via-violet-300 to-cyan-300 bg-clip-text text-transparent">
              answered with proof.
            </span>
          </h1>
          <p className="mt-6 max-w-md text-base leading-relaxed text-white/55">
            Upload documents, search with hybrid AI retrieval, and get cited answers your team can trust.
          </p>

          <div className="mt-12 space-y-4">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className="flex items-start gap-4 rounded-2xl border border-white/8 bg-white/5 p-4 backdrop-blur-sm transition-colors hover:bg-white/8"
                style={{ animationDelay: `${i * 100}ms` }}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-white/10 to-white/5">
                  <f.icon className="h-5 w-5 text-blue-300" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{f.title}</p>
                  <p className="text-sm text-white/45">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 border-t border-white/10 px-12 py-6">
          <div className="flex gap-8 text-center">
            {[
              { v: "100M+", l: "Chunks scaled" },
              { v: "99.9%", l: "Uptime SLA" },
              { v: "<2s", l: "Avg retrieval" },
            ].map((s) => (
              <div key={s.l}>
                <p className="text-2xl font-bold text-white">{s.v}</p>
                <p className="text-xs text-white/40">{s.l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Auth panel ─────────────────────────────────────── */}
      <div className="relative flex flex-1 flex-col items-center justify-center bg-gradient-to-br from-slate-50 via-white to-blue-50/40 px-6 py-12">
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -right-32 -top-32 h-64 w-64 rounded-full bg-blue-100/60 blur-3xl" />
          <div className="absolute -bottom-32 -left-32 h-64 w-64 rounded-full bg-violet-100/50 blur-3xl" />
        </div>

        <div className="relative w-full max-w-[420px] animate-fade-up">
          {/* Mobile logo */}
          <div className="mb-8 flex items-center justify-center gap-3 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-violet-600">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <span className="text-lg font-bold">Enterprise RAG</span>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold tracking-tight text-foreground">
              {isRegister ? "Create your workspace" : "Welcome back"}
            </h2>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {isRegister
                ? "Set up your organization and start building your knowledge base"
                : "Sign in to continue to your knowledge assistant"}
            </p>
          </div>

          {/* Tab switcher */}
          <div className="mb-6 flex rounded-xl bg-muted/60 p-1">
            {(["Sign in", "Register"] as const).map((tab) => {
              const register = tab === "Register";
              const active = isRegister === register;
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => {
                    setIsRegister(register);
                    setError("");
                  }}
                  className={cn(
                    "flex-1 rounded-lg py-2.5 text-sm font-semibold transition-all duration-200",
                    active
                      ? "bg-white text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tab}
                </button>
              );
            })}
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {isRegister && (
              <div className="space-y-5 animate-fade-in">
                <AuthField
                  id="full_name"
                  label="Full name"
                  icon={User}
                  value={form.full_name}
                  onChange={(v) => setForm({ ...form, full_name: v })}
                  placeholder="Jane Smith"
                  required
                  autoComplete="name"
                />
                <AuthField
                  id="organization"
                  label="Organization"
                  icon={Building2}
                  value={form.organization_name}
                  onChange={(v) => setForm({ ...form, organization_name: v })}
                  placeholder="Acme Corporation"
                  autoComplete="organization"
                />
              </div>
            )}

            <AuthField
              id="email"
              label="Email address"
              type="email"
              icon={Mail}
              value={form.email}
              onChange={(v) => setForm({ ...form, email: v })}
              placeholder="you@company.com"
              required
              autoComplete="email"
            />

            <AuthField
              id="password"
              label="Password"
              type="password"
              icon={Lock}
              value={form.password}
              onChange={(v) => setForm({ ...form, password: v })}
              placeholder="Min. 8 characters"
              required
              minLength={8}
              autoComplete={isRegister ? "new-password" : "current-password"}
            />

            {!isRegister && (
              <div className="flex items-center justify-between text-sm">
                <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary/20"
                  />
                  Remember me
                </label>
                <button type="button" className="font-medium text-primary hover:text-primary/80">
                  Forgot password?
                </button>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive animate-fade-in">
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-destructive" />
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              className={cn(
                "group h-12 w-full rounded-xl text-base font-semibold shadow-lg shadow-primary/20",
                "bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700",
                "transition-all duration-200 hover:shadow-xl hover:shadow-primary/25"
              )}
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isRegister ? "Creating account…" : "Signing in…"}
                </>
              ) : (
                <>
                  {isRegister ? "Create account" : "Sign in"}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </Button>
          </form>

          {/* Demo accounts */}
          {!isRegister && (
            <div className="mt-8 animate-fade-in">
              <p className="mb-3 text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Quick demo access
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {DEMO_ACCOUNTS.map((demo) => (
                  <button
                    key={demo.label}
                    type="button"
                    onClick={() => fillDemo(demo.email, demo.password)}
                    className="rounded-full border border-border/80 bg-white/80 px-4 py-1.5 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur-sm transition-all hover:border-primary/30 hover:text-primary hover:shadow"
                  >
                    {demo.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="mt-8 text-center text-xs text-muted-foreground/70">
            By continuing, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </div>
    </div>
  );
}
