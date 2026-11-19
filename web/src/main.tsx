import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/tokens.css";
import "./styles/look.css";
import "./styles/app.css";

import * as Tooltip from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, Outlet, RouterProvider, createRootRoute, createRoute, createRouter, redirect } from "@tanstack/react-router";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity } from "./Activity";
import { RunSheetProvider } from "./RunSheet";
import { ComparePage } from "./pages/Compare";
import { JobPage } from "./pages/Job";
import { RunPage } from "./pages/Run";
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
  return <button className="btn sm" type="button" onClick={flip}>{theme === "dark" ? "Light" : "Dark"}</button>;
}

function Layout() {
  const nav: [string, string][] = [["/targets", "Targets"], ["/runs", "Runs"], ["/compare", "Compare"], ["/tests", "Tests"]];
  return (
    <RunSheetProvider>
      <header className="topbar">
        <span className="brand">SAI Conformance</span>
        <nav className="nav">
          {nav.map(([to, label]) => (
            <Link key={to} to={to} activeProps={{ "aria-current": "page" }} activeOptions={{ includeSearch: false }}>{label}</Link>
          ))}
        </nav>
        <span className="spacer" />
        <div className="tools"><Activity /><span className="kbd" title="Command palette comes later">⌘K</span><ThemeButton /></div>
      </header>
      <main className="page"><Outlet /></main>
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
  component: function RunRoute() {
    const { runId } = runRoute.useParams();
    return <RunPage key={runId} runId={runId} />;
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
const testsRoute = createRoute({ getParentRoute: () => rootRoute, path: "/tests", component: TestsPage });

const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, targetsRoute, runsRoute, runRoute, jobRoute, compareRoute, testsRoute]),
  defaultNotFoundComponent: () => <section className="section"><h1>Not found</h1><p className="muted">Try <Link to="/targets">Targets</Link>.</p></section>,
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
