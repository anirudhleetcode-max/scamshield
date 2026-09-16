import { Suspense, lazy, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import Check from "./pages/Check";
import Links from "./pages/Links";
import Reports from "./pages/Reports";
import History from "./pages/History";
const Insights = lazy(() => import("./pages/Insights"));

const KEYS: Record<string, string> = { "1": "/", "2": "/links", "3": "/reports", "4": "/history", "5": "/insights" };

function Hotkeys() {
  const nav = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.altKey || e.ctrlKey || e.metaKey || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
      if (KEYS[e.key]) nav(KEYS[e.key]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);
  return null;
}

function Routed() {
  const { user, loading } = useAuth();
  if (loading) return <div className="empty">Loading…</div>;
  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  return (
    <>
      <Hotkeys />
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Check />} />
          <Route path="links" element={<Links />} />
          <Route path="reports" element={<Reports />} />
          <Route path="history" element={<History />} />
          <Route path="insights" element={<Suspense fallback={<div className="empty">Loading insights…</div>}><Insights /></Suspense>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routed />
      </AuthProvider>
    </BrowserRouter>
  );
}
