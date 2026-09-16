import { NavLink, Outlet } from "react-router-dom";
import { BarChart3, Cpu, Flag, History, Link2, LogOut, MessageSquareWarning } from "lucide-react";
import { useAuth } from "../lib/auth";
import { ShieldMark } from "./ShieldMark";

const NAV = [
  { to: "/", label: "Check", icon: MessageSquareWarning, k: "1" },
  { to: "/links", label: "UPI & Links", icon: Link2, k: "2" },
  { to: "/reports", label: "Reports", icon: Flag, k: "3" },
  { to: "/history", label: "History", icon: History, k: "4" },
  { to: "/insights", label: "Insights", icon: BarChart3, k: "5" },
  { to: "/model", label: "Model", icon: Cpu, k: "6" },
];

function Nav() {
  return (
    <nav className="nav" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon, k }) => (
        <NavLink key={to} to={to} end={to === "/"}>
          <Icon size={16} strokeWidth={1.75} aria-hidden />
          {label}
          <span className="k">{k}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export default function Shell() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <ShieldMark />
          <span className="brand-name">ScamShield</span>
          <span className="brand-tag">IN</span>
        </div>
        <Nav />
        <div className="helpline">
          Lost money to a scam?
          <b>Call 1930</b>
          or report at <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">cybercrime.gov.in</a>
        </div>
        <div className="side-foot">
          <div className="who" title={user?.email}>{user?.name}</div>
          <div className="muted" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{user?.email}</div>
          <button className="btn ghost sm" style={{ marginTop: 8 }} onClick={logout}>
            <LogOut size={14} aria-hidden /> Sign out
          </button>
        </div>
      </aside>
      <header className="topbar">
        <div className="brand">
          <ShieldMark />
          <span className="brand-name">ScamShield</span>
          <button className="btn ghost sm" onClick={logout} aria-label="Sign out"><LogOut size={14} /></button>
        </div>
        <Nav />
      </header>
      <div style={{ minWidth: 0 }}>
        {user?.is_demo && (
          <div className="demo-banner" role="note" data-testid="demo-banner">
            Demo account — the history, reports and charts here are seeded sample data generated for this demo, not real user activity.
          </div>
        )}
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
