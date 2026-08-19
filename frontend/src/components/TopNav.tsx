import { Zap, Type, Settings, Activity, Grid, Clock, Database } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";

interface StepDef {
  label: string;
  icon: typeof Type;
  path: string | null; // null = display-only step, not directly navigable
  isCurrent: (pathname: string) => boolean;
}

const steps: StepDef[] = [
  { label: "1. Keywords", icon: Type, path: "/keywords", isCurrent: (path) => path === "/keywords" },
  { label: "2. Configure", icon: Settings, path: null, isCurrent: (path) => path === "/collections/new" },
  { label: "3. Collect", icon: Activity, path: null, isCurrent: (path) => path.endsWith("/progress") },
  {
    label: "4. Results",
    icon: Grid,
    path: null,
    isCurrent: (path) => /^\/collections\/COL-\d+(?:\/graph)?$/.test(path),
  },
];

export default function TopNav() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="flex items-center justify-between px-8 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600">
            <Zap className="h-5 w-5 text-white" fill="white" />
          </div>
          <div>
            <div className="text-lg font-bold text-emerald-600">yonnov'IA</div>
            <div className="text-xs text-slate-400">
              Plateforme intelligente de scraping d'articles scientifiques
            </div>
          </div>
        </div>

        <nav className="flex items-center gap-2">
          {steps.map((step, i) => {
            const active = step.isCurrent(location.pathname);
            const clickable = Boolean(step.path);
            return (
              <div key={step.label} className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!clickable}
                  onClick={() => step.path && navigate(step.path)}
                  className={`flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                      : clickable
                        ? "text-slate-400 hover:text-slate-600"
                        : "cursor-not-allowed text-slate-300"
                  }`}
                >
                  <step.icon className="h-4 w-4" />
                  {step.label}
                </button>
                {i < steps.length - 1 && <div className="h-px w-6 bg-slate-200" />}
              </div>
            );
          })}
        </nav>

        <div className="flex items-center gap-4 text-sm">
          <button
            onClick={() => navigate("/sources")}
            className={`flex items-center gap-1.5 ${
              location.pathname.startsWith("/sources")
                ? "font-medium text-emerald-700"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Database className="h-4 w-4" />
            Sources
          </button>
          <button
            onClick={() => navigate("/history")}
            className={`flex items-center gap-1.5 ${
              location.pathname.startsWith("/history")
                ? "font-medium text-emerald-700"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Clock className="h-4 w-4" />
            History
          </button>
          <div className="h-5 w-px bg-slate-200" />
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-xs font-bold text-white">
              T8
            </div>
            <span className="text-slate-700">Team08-E26</span>
          </div>
        </div>
      </div>
    </header>
  );
}
