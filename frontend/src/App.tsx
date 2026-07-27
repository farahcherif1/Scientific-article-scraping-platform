import { Routes, Route, Navigate } from "react-router-dom";
import KeywordsPage from "./pages/KeywordsPage";
import ConfigurePage from "./pages/ConfigurePage";
import HistoryPage from "./pages/HistoryPage";
import CollectionPage from "./pages/CollectionPage";
import ResultsPlaceholderPage from "./pages/ResultsPlaceholderPage";
import SourcesPage from "./pages/SourcesPage";
import CustomConnectorWizardPage from "./pages/CustomConnectorWizardPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/keywords" replace />} />
      <Route path="/keywords" element={<KeywordsPage />} />
      <Route path="/collections/new" element={<ConfigurePage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/collections/:id/progress" element={<CollectionPage />} />
      <Route path="/collections/:id" element={<ResultsPlaceholderPage />} />
      <Route path="/sources" element={<SourcesPage />} />
      <Route path="/sources/custom/new" element={<CustomConnectorWizardPage />} />
      <Route path="/sources/custom/:slug/edit" element={<CustomConnectorWizardPage />} />
    </Routes>
  );
}

export default App;
