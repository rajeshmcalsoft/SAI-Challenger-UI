// A small inline icon set (24×24 strokes), so the app needs no icon package and works offline.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

function Svg({ children, ...p }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" {...p}>
      {children}
    </svg>
  );
}

export const I = {
  check: (p: P) => <Svg strokeWidth={3.2} {...p}><path d="M5 12.5l4.5 4.5L19 7.5" /></Svg>,
  x: (p: P) => <Svg strokeWidth={3.2} {...p}><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" /></Svg>,
  bang: (p: P) => <Svg strokeWidth={3.4} {...p}><path d="M12 5v9" /><path d="M12 19h.01" /></Svg>,
  diamond: (p: P) => <Svg strokeWidth={0} {...p}><path d="M12 4l8 8-8 8-8-8z" fill="currentColor" /></Svg>,
  up: (p: P) => <Svg strokeWidth={3} {...p}><path d="M12 19V6M6 11.5L12 5.5l6 6" /></Svg>,
  minus: (p: P) => <Svg strokeWidth={3.4} {...p}><path d="M6 12h12" /></Svg>,
  chevron: (p: P) => <Svg {...p}><path d="M6 9l6 6 6-6" /></Svg>,
  chevronUp: (p: P) => <Svg {...p}><path d="M6 15l6-6 6 6" /></Svg>,
  chevronRight: (p: P) => <Svg {...p}><path d="M9 6l6 6-6 6" /></Svg>,
  search: (p: P) => <Svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4-4" /></Svg>,
  copy: (p: P) => <Svg {...p}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></Svg>,
  split: (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M11 4v16" /></Svg>,
  full: (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /></Svg>,
  sun: (p: P) => <Svg {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Svg>,
  moon: (p: P) => <Svg {...p}><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></Svg>,
  retry: (p: P) => <Svg {...p}><path d="M20 11a8 8 0 0 0-14.5-4.5L4 8" /><path d="M4 4v4h4" /><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16" /><path d="M20 20v-4h-4" /></Svg>,
  flaky: (p: P) => <Svg {...p}><path d="M3 12h3l2-5 4 10 3-7 2 2h4" /></Svg>,
  plusCircle: (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 8.5v7M8.5 12h7" /></Svg>,
  fixed: (p: P) => <Svg {...p}><path d="M7 17L17 7M9 7h8v8" /></Svg>,
  regressed: (p: P) => <Svg {...p}><path d="M7 7l10 10M17 9v8H9" /></Svg>,
  clock: (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Svg>,
  bug: (p: P) => <Svg {...p}><rect x="7" y="7" width="10" height="13" rx="5" /><path d="M12 11v9M7 13H3M21 13h-4M7 17l-3 2M17 17l3 2M9 7l-1-3M15 7l1-3" /></Svg>,
  hourglass: (p: P) => <Svg {...p}><path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9" /></Svg>,
  shield: (p: P) => <Svg {...p}><path d="M12 3l8 3v6c0 4.5-3.5 8-8 9-4.5-1-8-4.5-8-9V6z" /><path d="M8.5 12l2.5 2.5L15.5 10" /></Svg>,
  external: (p: P) => <Svg {...p}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>,
  download: (p: P) => <Svg {...p}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></Svg>,
  file: (p: P) => <Svg {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></Svg>,
  list: (p: P) => <Svg {...p}><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" /></Svg>,
  chart: (p: P) => <Svg {...p}><path d="M4 20V10M10 20V4M16 20v-7M21 20H3" /></Svg>,
  server: (p: P) => <Svg {...p}><rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01M7 16.5h.01" /></Svg>,
  play: (p: P) => <Svg {...p}><path d="M7 4.5v15l12-7.5z" /></Svg>,
  compare: (p: P) => <Svg {...p}><rect x="3" y="4" width="7" height="16" rx="1.5" /><rect x="14" y="4" width="7" height="16" rx="1.5" /></Svg>,
  flask: (p: P) => <Svg {...p}><path d="M9 3h6M10 3v6l-5.5 9.5A1.6 1.6 0 0 0 5.9 21h12.2a1.6 1.6 0 0 0 1.4-2.5L14 9V3" /><path d="M7.5 15h9" /></Svg>,
  layers: (p: P) => <Svg {...p}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></Svg>,
  tests: (p: P) => <Svg {...p}><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4V3h6v1M9 11l2 2 4-4M9 17h6" /></Svg>,
  ports: (p: P) => <Svg {...p}><rect x="3" y="7" width="18" height="10" rx="2" /><path d="M7 11h2v2H7zM11 11h2v2h-2zM15 11h2v2h-2z" /></Svg>,
  more: (p: P) => <Svg {...p}><path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth={3} /></Svg>,
  robot: (p: P) => <Svg {...p}><rect x="4" y="8" width="16" height="12" rx="3" /><path d="M12 8V4M9 13h.01M15 13h.01M9 17h6" /></Svg>,
  causes: (p: P) => <Svg {...p}><path d="M4 5h16l-6 7v6l-4 2v-8z" /></Svg>,
  info: (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></Svg>,
  close: (p: P) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>,
  expand: (p: P) => <Svg {...p}><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7" /></Svg>,
  home: (p: P) => <Svg {...p}><path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" /></Svg>,
  eye: (p: P) => <Svg {...p}><path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.5" /></Svg>,
  link: (p: P) => <Svg {...p}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></Svg>,
};

/** The app's mark: a switch front panel with one port lit. */
export function Logo() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect x="2.5" y="6" width="19" height="12" rx="3" fill="none" stroke="var(--accent-text)" strokeWidth="2" />
      <rect x="6" y="10" width="3" height="4" rx="1" fill="var(--pass)" />
      <rect x="10.5" y="10" width="3" height="4" rx="1" fill="var(--gap)" />
      <rect x="15" y="10" width="3" height="4" rx="1" fill="var(--fail)" />
    </svg>
  );
}
