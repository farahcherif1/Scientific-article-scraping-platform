import { Routes, Route, Navigate } from "react-router-dom";
import KeywordsPage from "./pages/KeywordsPage";
import ConfigurePage from "./pages/ConfigurePage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/keywords" replace />} />
      <Route path="/keywords" element={<KeywordsPage />} />
      <Route path="/collections/new" element={<ConfigurePage />} />
    </Routes>
  );
}

export default App;
