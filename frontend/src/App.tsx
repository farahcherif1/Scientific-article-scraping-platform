import { useState } from "react";
import KeywordsPage from "./pages/KeywordsPage";
import HistoryPage from "./pages/HistoryPage";

type Page = "keywords" | "history";

function App() {
  const [page, setPage] = useState<Page>("keywords");

  if (page === "history") {
    return (
      <HistoryPage
        onStartNewCollection={() => setPage("keywords")}
        onOpenCollection={() => setPage("keywords")}
      />
    );
  }

  return <KeywordsPage onNavigateHistory={() => setPage("history")} />;
}

export default App;
