import { useParams, useNavigate } from "react-router-dom";
import { Construction } from "lucide-react";
import TopNav from "../components/TopNav";

/**
 * Temporary stand-in for the Results page (EP-05), which hasn't been built yet.
 * Lets History rows be clickable without dead-ending on a blank screen.
 */
export default function ResultsPlaceholderPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />
      <main className="mx-auto flex max-w-7xl flex-col items-center justify-center gap-3 px-8 py-24 text-center">
        <Construction className="h-8 w-8 text-slate-300" />
        <h1 className="text-xl font-semibold text-slate-700">
          Results view for collection #{id}
        </h1>
        <p className="max-w-md text-sm text-slate-400">
          The results screen is planned for EP-05 and isn't built yet.
        </p>
        <button
          onClick={() => navigate("/history")}
          className="mt-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Back to History
        </button>
      </main>
    </div>
  );
}
