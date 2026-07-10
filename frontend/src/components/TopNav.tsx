import { Zap, Type, Settings, Activity, Grid, Clock } from "lucide-react";

export type Page = "keywords" | "history";

const steps: { label: string; icon: typeof Type; page: Page }[] = [
  { label: "1. Keywords", icon: Type, page: "keywords" },
  { label: "2. Configure", icon: Settings, page: "keywords" },
  { label: "3. Collect", icon: Activity, page: "keywords" },
  { label: "4. Results", icon: Grid, page: "keywords" },
];

interface Props {
  current: Page;
  onNavigate: (page: Page) => void;
}

export default function TopNav({ current, onNavigate }: Props) {
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
            const active = current === "keywords" && step.label.startsWith("1.");
            return (
              <div key={step.label} className="flex items-center gap-2">
                <div
                  className={`flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium ${
                    active
                      ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "text-slate-400"
                  }`}
                >
                  <step.icon className="h-4 w-4" />
                  {step.label}
                </div>
                {i < steps.length - 1 && <div className="h-px w-6 bg-slate-200" />}
              </div>
            );
          })}
        </nav>

        <div className="flex items-center gap-4 text-sm">
          <button
            onClick={() => onNavigate("history")}
            className={`flex items-center gap-1.5 ${
              current === "history"
                ? "font-medium text-emerald-600"
                : "text-slate-500 hover:text-emerald-600"
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
