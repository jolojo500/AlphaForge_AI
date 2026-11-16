import React from 'react';
import { TraceEntry } from '../types';
import { type Lang } from '@/lib/format';

/**
 * The LangGraph graph drawn as an SVG that fills in as trace events arrive:
 * finished nodes are solid, the node in progress pulses, the rest stay outlined.
 * Edges "draw" themselves once both ends are done; the two retry loops light up
 * only when a node is run a second time.
 */

type NodeId =
  | 'profile'
  | 'screening'
  | 'quant'
  | 'macro'
  | 'events'
  | 'scenarios'
  | 'red_team'
  | 'explain'
  | 'verifier';

const W = 100;
const H = 30;

const NODES: Record<NodeId, { x: number; y: number; fr: string; en: string; llm: boolean }> = {
  profile: { x: 160, y: 28, fr: 'Profil', en: 'Profile', llm: true },
  screening: { x: 160, y: 92, fr: 'Filtrage', en: 'Screening', llm: false },
  quant: { x: 56, y: 162, fr: 'Quant', en: 'Quant', llm: false },
  macro: { x: 160, y: 162, fr: 'Macro', en: 'Macro', llm: false },
  events: { x: 264, y: 162, fr: 'Actualités', en: 'News', llm: true },
  scenarios: { x: 160, y: 232, fr: 'Scénarios', en: 'Scenarios', llm: false },
  red_team: { x: 160, y: 296, fr: 'Red team', en: 'Red team', llm: true },
  explain: { x: 160, y: 360, fr: 'Explication', en: 'Explanation', llm: true },
  verifier: { x: 160, y: 424, fr: 'Vérification', en: 'Verifier', llm: false },
};

const EDGES: Array<[NodeId, NodeId]> = [
  ['profile', 'screening'],
  ['screening', 'quant'],
  ['screening', 'macro'],
  ['screening', 'events'],
  ['quant', 'scenarios'],
  ['macro', 'scenarios'],
  ['events', 'scenarios'],
  ['scenarios', 'red_team'],
  ['red_team', 'explain'],
  ['explain', 'verifier'],
];

const LOOPS: Array<{ from: NodeId; to: NodeId; side: 1 | -1 }> = [
  { from: 'red_team', to: 'scenarios', side: 1 },
  { from: 'verifier', to: 'explain', side: 1 },
];

function edgePath(a: NodeId, b: NodeId): { d: string; len: number } {
  const A = NODES[a];
  const B = NODES[b];
  const x1 = A.x;
  const y1 = A.y + H / 2;
  const x2 = B.x;
  const y2 = B.y - H / 2;
  if (x1 === x2) {
    return { d: `M ${x1} ${y1} L ${x2} ${y2}`, len: y2 - y1 };
  }
  // fan out / fan in through a horizontal bus halfway down
  const ym = (y1 + y2) / 2;
  const len = Math.abs(ym - y1) + Math.abs(x2 - x1) + Math.abs(y2 - ym);
  return { d: `M ${x1} ${y1} L ${x1} ${ym} L ${x2} ${ym} L ${x2} ${y2}`, len };
}

function loopPath(from: NodeId, to: NodeId, side: 1 | -1): { d: string; len: number } {
  const F = NODES[from];
  const T = NODES[to];
  const x = F.x + side * (W / 2);
  const bulge = x + side * 34;
  const y1 = F.y;
  const y2 = T.y;
  const d = `M ${x} ${y1} C ${bulge} ${y1}, ${bulge} ${y2}, ${x} ${y2}`;
  return { d, len: Math.abs(y1 - y2) + 70 };
}

interface GraphProgressProps {
  trace: TraceEntry[];
  lang: Lang;
  className?: string;
}

export const GraphProgress: React.FC<GraphProgressProps> = ({ trace, lang, className }) => {
  const counts = new Map<string, number>();
  for (const e of trace) counts.set(e.node, (counts.get(e.node) ?? 0) + 1);
  const isDone = (n: NodeId) => (counts.get(n) ?? 0) > 0;

  // The node in progress: first unfinished node in graph order. The three analyses run in
  // parallel, so when screening is done and any of them is missing, all missing ones pulse.
  const order: NodeId[] = ['profile', 'screening', 'quant', 'macro', 'events', 'scenarios', 'red_team', 'explain', 'verifier'];
  const parallel: NodeId[] = ['quant', 'macro', 'events'];
  const firstPending = order.find((n) => !isDone(n)) ?? null;
  const active = new Set<NodeId>();
  if (firstPending) {
    if (parallel.includes(firstPending) && isDone('screening')) {
      parallel.filter((n) => !isDone(n)).forEach((n) => active.add(n));
    } else {
      active.add(firstPending);
    }
  }
  // A what-if rerun starts at screening: profile is then "done" implicitly.
  const skipProfile = !isDone('profile') && isDone('screening');

  const nodeState = (n: NodeId): 'done' | 'active' | 'pending' => {
    if (isDone(n) || (n === 'profile' && skipProfile)) return 'done';
    if (active.has(n)) return 'active';
    return 'pending';
  };

  const title = lang === 'en' ? 'Analysis graph progress' : "Progression du graphe d'analyse";

  return (
    <svg
      viewBox="0 0 320 450"
      role="img"
      aria-label={title}
      className={className}
      style={{ width: '100%', maxWidth: 320, height: 'auto' }}
    >
      <title>{title}</title>
      <defs>
        <marker id="gp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="fill-primary" />
        </marker>
        <marker id="gp-arrow-muted" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" className="fill-border" />
        </marker>
      </defs>

      {/* edges: muted underlay, then the primary stroke that draws itself when both ends are done */}
      {EDGES.map(([a, b]) => {
        const { d, len } = edgePath(a, b);
        const lit = nodeState(a) === 'done' && nodeState(b) !== 'pending';
        return (
          <g key={`${a}-${b}`}>
            <path d={d} fill="none" className="stroke-border" strokeWidth={1.5} markerEnd="url(#gp-arrow-muted)" />
            <path
              d={d}
              fill="none"
              className="stroke-primary"
              strokeWidth={2}
              strokeDasharray={len}
              strokeDashoffset={lit ? 0 : len}
              style={{ transition: 'stroke-dashoffset 700ms ease-out' }}
              markerEnd={lit ? 'url(#gp-arrow)' : undefined}
            />
          </g>
        );
      })}

      {/* retry loops: dashed, lit only when the target ran again */}
      {LOOPS.map(({ from, to, side }) => {
        const { d, len } = loopPath(from, to, side);
        const lit = (counts.get(to) ?? 0) >= 2;
        return (
          <g key={`loop-${from}`}>
            <path d={d} fill="none" className="stroke-border" strokeWidth={1.25} strokeDasharray="4 4" markerEnd="url(#gp-arrow-muted)" />
            <path
              d={d}
              fill="none"
              className="stroke-primary"
              strokeWidth={2}
              strokeDasharray={len}
              strokeDashoffset={lit ? 0 : len}
              style={{ transition: 'stroke-dashoffset 700ms ease-out' }}
              markerEnd={lit ? 'url(#gp-arrow)' : undefined}
            />
          </g>
        );
      })}

      {/* nodes */}
      {(Object.keys(NODES) as NodeId[]).map((id) => {
        const n = NODES[id];
        const state = nodeState(id);
        const label = lang === 'en' ? n.en : n.fr;
        const x = n.x - W / 2;
        const y = n.y - H / 2;
        return (
          <g key={id} style={{ transition: 'opacity 300ms' }}>
            {state === 'active' && (
              <rect
                x={x - 4}
                y={y - 4}
                width={W + 8}
                height={H + 8}
                rx={10}
                className="fill-primary/15 animate-pulse"
              />
            )}
            <rect
              x={x}
              y={y}
              width={W}
              height={H}
              rx={7}
              className={
                state === 'done'
                  ? 'fill-primary stroke-primary'
                  : state === 'active'
                  ? 'fill-background stroke-primary'
                  : 'fill-background stroke-border'
              }
              strokeWidth={state === 'pending' ? 1.25 : 2}
              strokeDasharray={state === 'active' ? '5 3' : undefined}
              style={{ transition: 'fill 400ms, stroke 400ms' }}
            >
              {state === 'active' && (
                <animate attributeName="stroke-dashoffset" from="0" to="-16" dur="1s" repeatCount="indefinite" />
              )}
            </rect>
            <text
              x={n.x}
              y={n.y + 4}
              textAnchor="middle"
              fontSize={11}
              fontWeight={state === 'pending' ? 400 : 600}
              className={
                state === 'done'
                  ? 'fill-primary-foreground'
                  : state === 'active'
                  ? 'fill-foreground'
                  : 'fill-muted-foreground'
              }
            >
              {label}
            </text>
            {n.llm && (
              <circle cx={x + W - 7} cy={y + 7} r={2.5} className={state === 'done' ? 'fill-primary-foreground/70' : 'fill-ring'}>
                <title>{lang === 'en' ? 'LLM agent' : 'Agent LLM'}</title>
              </circle>
            )}
          </g>
        );
      })}
    </svg>
  );
};
