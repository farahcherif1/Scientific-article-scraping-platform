import { Routes, Route, Navigate } from "react-router-dom";
import KeywordsPage from "./pages/KeywordsPage";
import ConfigurePage from "./pages/ConfigurePage";
import HistoryPage from "./pages/HistoryPage";
import ResultsPlaceholderPage from "./pages/ResultsPlaceholderPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/keywords" replace />} />
      <Route path="/keywords" element={<KeywordsPage />} />
      <Route path="/collections/new" element={<ConfigurePage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/collections/:id" element={<ResultsPlaceholderPage />} />
    </Routes>
  );
}

export default App;
