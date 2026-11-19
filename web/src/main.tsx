import "./styles/tokens.css";
import "./styles/look.css";
import "./styles/app.css";

import * as Tooltip from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, Outlet, RouterProvider, createRootRoute, createRoute, createRouter, redirect, useRouterState } from "@tanstack/react-router";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity } from "./Activity";
import { useHealth } from "./api";
import { I, Logo } from "./icons";
import { RunSheetProvider } from "./RunSheet";
import { ComparePage } from "./pages/Compare";
import { JobPage } from "./pages/Job";
import { RunPage, type RunSearch } from "./pages/Run";
import { RunsPage } from "./pages/Runs";
import { TargetsPage } from "./pages/Targets";
import { TestsPage } from "./pages/Tests";

function ThemeButton() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  const flip = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("sai-challenger-ui-theme", next); } catch { /* private window: theme just isn't remembered */ }
    setTheme(next);
  };
  return (
    <button className="btn ghost icon" type="button" onClick={flip} aria-label={theme === "dark" ? "Light theme" : "Dark theme"}
      title={theme === "dark" ? "Light theme" : "Dark theme"}>
      {theme === "dark" ? <I.sun /> : <I.moon />}
    </button>
  );
}

function Footer() {
  const health = useHealth();
  return (
    <footer className="foot">
      <span><b>SAI Conformance</b> · reads {health.data ? <span className="mono">{health.data.scRoot}</span> : "the SAI-Challenger checkout"}; runs go through scripts/poc/run_poc.sh</span>
      <span>Look after Allure Report (Apache-2.0) · fonts PT Root UI and JetBrains Mono (OFL)</span>
    </footer>
  );
}

function Layout() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const wide = /^\/(runs\/[^/]+|jobs\/|tests)/.test(path);
  const nav: [string, string, (p: { className?: string }) => React.ReactNode][] = [
    ["/targets", "Targets", I.server], ["/runs", "Runs", I.play], ["/compare", "Compare", I.compare], ["/tests", "Tests", I.tests],
  ];
  return (
    <RunSheetProvider>
      <header className="topbar">
        <Link to="/targets" className="brand"><span className="logo"><Logo /></span>SAI Conformance</Link>
        <nav className="nav" aria-label="Sections">
          {nav.map(([to, label, Icon]) => (
            <Link key={to} to={to} activeProps={{ "aria-current": "page" }} activeOptions={{ includeSearch: false }}><Icon /><span>{label}</span></Link>
          ))}
        </nav>
        <span className="spacer" />
        <div className="tools"><Activity /><span className="kbd" title="Command palette comes later">⌘K</span><ThemeButton /></div>
      </header>
      <main className={`page${wide ? " wide" : ""}`}><Outlet /></main>
      <Footer />
    </RunSheetProvider>
  );
}

const rootRoute = createRootRoute({ component: Layout });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/targets" }); } });
const targetsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/targets", component: TargetsPage });
const runsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/runs", component: RunsPage });
const runRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs/$runId",
  validateSearch: (s: Record<string, unknown>): RunSearch => ({
    t: typeof s.t === "string" && s.t ? s.t : undefined,
    view: s.view === "charts" ? "charts" : undefined,
    tab: ["causes", "gates", "log"].includes(String(s.tab)) ? (s.tab as RunSearch["tab"]) : undefined,
  }),
  component: function RunRoute() {
    const { runId } = runRoute.useParams();
    const search = runRoute.useSearch();
    return <RunPage key={runId} runId={runId} search={search} />;
  },
});
const jobRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/jobs/$jobId",
  component: function JobRoute() {
    const { jobId } = jobRoute.useParams();
    return <JobPage key={jobId} jobId={jobId} />;
  },
});
const compareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/compare",
  validateSearch: (s: Record<string, unknown>): { tab: string } => ({
    tab: ["matrix", "diff", "gaps"].includes(String(s.tab)) ? String(s.tab) : "matrix",
  }),
  component: function CompareRoute() {
    const { tab } = compareRoute.useSearch();
    return <ComparePage tab={tab} />;
  },
});
const testsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tests",
  validateSearch: (s: Record<string, unknown>): { t?: string } => ({ t: typeof s.t === "string" && s.t ? s.t : undefined }),
  component: function TestsRoute() {
    const { t } = testsRoute.useSearch();
    return <TestsPage selected={t ?? null} />;
  },
});

const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, targetsRoute, runsRoute, runRoute, jobRoute, compareRoute, testsRoute]),
  defaultNotFoundComponent: () => <div className="card"><h1>Not found</h1><p className="muted">Try <Link to="/targets">Targets</Link>.</p></div>,
});

declare module "@tanstack/react-router" {
  interface Register { router: typeof router }
}

const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 5000, retry: 1 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queries}>
      <Tooltip.Provider delayDuration={120}>
        <RouterProvider router={router} />
      </Tooltip.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
