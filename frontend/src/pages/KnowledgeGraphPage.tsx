import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Info, Loader2, Orbit, RotateCcw } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import TopNav from "../components/TopNav";
import { fetchKnowledgeGraph, type KnowledgeGraph, type KnowledgeGraphNode } from "../api/articles";

type NodeType = KnowledgeGraphNode["type"];
type Point = { x: number; y: number; z: number };

const COLORS: Record<NodeType, string> = { article: "#10b981", author: "#60a5fa", keyword: "#fbbf24", year: "#c084fc" };
const NAMES: Record<NodeType, string> = { article: "Articles", author: "Authors", keyword: "Keywords", year: "Years" };
const ALL_TYPES: NodeType[] = ["article", "author", "keyword", "year"];

function pointFor(index: number, total: number): Point {
  // A Fibonacci sphere distributes nodes in 3D space before projection.
  const y = index * (2 / total) - 1 + 1 / total;
  const angle = index * Math.PI * (3 - Math.sqrt(5));
  const radius = Math.sqrt(1 - y * y);
  return { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius };
}

function GraphCanvas({ graph, enabled, onSelect }: { graph: KnowledgeGraph; enabled: Set<NodeType>; onSelect: (node: KnowledgeGraphNode | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const view = useRef({ pitch: -0.3, yaw: 0.55, zoom: 1 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [reset, setReset] = useState(0);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const positions = new Map(graph.nodes.map((n, i) => [n.id, pointFor(i, Math.max(graph.nodes.length, 1))]));
    const nodes = new Map(graph.nodes.map((node) => [node.id, node]));
    let displayed: Array<{ node: KnowledgeGraphNode; x: number; y: number; radius: number; depth: number }> = [];

    const draw = () => {
      const box = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, box.width * dpr); canvas.height = Math.max(1, box.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = "#081827"; ctx.fillRect(0, 0, box.width, box.height);
      const cy = Math.cos(view.current.yaw), sy = Math.sin(view.current.yaw), cx = Math.cos(view.current.pitch), sx = Math.sin(view.current.pitch);
      const project = (p: Point) => {
        const x1 = p.x * cy - p.z * sy, z1 = p.x * sy + p.z * cy;
        const y1 = p.y * cx - z1 * sx, z2 = p.y * sx + z1 * cx;
        const scale = Math.min(box.width, box.height) * 0.38 * view.current.zoom / (2.7 - z2);
        return { x: box.width / 2 + x1 * scale, y: box.height / 2 + y1 * scale, depth: z2 };
      };
      const projected = new Map([...positions].map(([id, point]) => [id, project(point)]));
      ctx.lineWidth = 1;
      for (const link of graph.links) {
        const source = nodes.get(link.source), target = nodes.get(link.target), a = projected.get(link.source), b = projected.get(link.target);
        if (!source || !target || !a || !b || !enabled.has(source.type) || !enabled.has(target.type)) continue;
        ctx.strokeStyle = "rgba(148, 163, 184, .35)"; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      displayed = graph.nodes.filter((n) => enabled.has(n.type)).map((node) => {
        const p = projected.get(node.id)!; return { node, ...p, radius: Math.max(3, (node.type === "article" ? 7 : 5) + p.depth * 1.3) };
      }).sort((a, b) => a.depth - b.depth);
      for (const item of displayed) { ctx.globalAlpha = Math.min(1, Math.max(.5, .75 + item.depth * .15)); ctx.fillStyle = COLORS[item.node.type]; ctx.beginPath(); ctx.arc(item.x, item.y, item.radius, 0, Math.PI * 2); ctx.fill(); }
      ctx.globalAlpha = 1;
    };
    const resize = new ResizeObserver(draw); resize.observe(canvas); draw();
    const down = (e: PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; canvas.setPointerCapture(e.pointerId); };
    const move = (e: PointerEvent) => { if (!drag.current) return; const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y; if (Math.abs(dx) + Math.abs(dy) > 2) drag.current.moved = true; view.current.yaw += dx * .009; view.current.pitch = Math.max(-1.5, Math.min(1.5, view.current.pitch + dy * .009)); drag.current.x = e.clientX; drag.current.y = e.clientY; draw(); };
    const up = (e: PointerEvent) => { const action = drag.current; drag.current = null; if (!action || action.moved) return; const rect = canvas.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top; let hit: KnowledgeGraphNode | null = null, distance = 18; for (const item of displayed) { const d = Math.hypot(item.x - x, item.y - y); if (d < distance) { distance = d; hit = item.node; } } onSelect(hit); };
    const wheel = (e: WheelEvent) => { e.preventDefault(); view.current.zoom = Math.max(.45, Math.min(2.2, view.current.zoom * (e.deltaY > 0 ? .9 : 1.1))); draw(); };
    canvas.addEventListener("pointerdown", down); canvas.addEventListener("pointermove", move); canvas.addEventListener("pointerup", up); canvas.addEventListener("wheel", wheel, { passive: false });
    return () => { resize.disconnect(); canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointermove", move); canvas.removeEventListener("pointerup", up); canvas.removeEventListener("wheel", wheel); };
  }, [graph, enabled, onSelect, reset]);

  return <div className="relative h-[600px] overflow-hidden rounded-xl border border-slate-700 shadow-lg"><canvas ref={ref} aria-label="Interactive 3D knowledge graph" className="h-full w-full touch-none cursor-grab active:cursor-grabbing" /><p className="pointer-events-none absolute bottom-4 left-4 rounded-lg bg-slate-950/80 px-3 py-2 text-xs text-slate-100">Drag to rotate · Scroll to zoom · Click a node for details</p><button onClick={() => { view.current = { pitch: -.3, yaw: .55, zoom: 1 }; setReset((n) => n + 1); }} className="absolute right-4 top-4 flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow hover:bg-slate-100"><RotateCcw className="h-4 w-4" /> Reset view</button></div>;
}

export default function KnowledgeGraphPage() {
  const { id = "" } = useParams(); const navigate = useNavigate();
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null); const [error, setError] = useState<string | null>(null); const [selected, setSelected] = useState<KnowledgeGraphNode | null>(null);
  const [enabled, setEnabled] = useState<Set<NodeType>>(new Set(ALL_TYPES));
  const select = useCallback((node: KnowledgeGraphNode | null) => setSelected(node), []);
  useEffect(() => { fetchKnowledgeGraph(id).then(setGraph).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load the knowledge graph.")); }, [id]);
  const toggle = (type: NodeType) => setEnabled((current) => {
    const next = new Set(current);
    if (next.has(type)) next.delete(type);
    else next.add(type);
    return next;
  });
  return <div className="min-h-screen bg-slate-50"><TopNav /><div className="h-0.5 bg-emerald-500" /><main className="mx-auto max-w-7xl px-8 py-8"><button onClick={() => navigate(`/collections/${id}`)} className="flex items-center gap-2 text-sm font-medium text-emerald-700 hover:underline"><ArrowLeft className="h-4 w-4" /> Back to results</button><div className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900"><Orbit className="h-6 w-6 text-emerald-600" /> 3D Knowledge Graph</h1><p className="mt-1 text-sm text-slate-500">Explore articles and their shared authors, keywords, and years.</p></div>{graph && <span className="rounded-lg bg-emerald-50 px-4 py-2 text-sm text-emerald-800">{graph.nodes.length} nodes · {graph.links.length} links</span>}</div>{error ? <div className="mt-8 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700"><AlertTriangle className="h-5 w-5" />{error}</div> : !graph ? <div className="flex h-96 items-center justify-center gap-3 text-slate-500"><Loader2 className="h-6 w-6 animate-spin" /> Loading graph…</div> : <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_260px]"><GraphCanvas graph={graph} enabled={enabled} onSelect={select} /><aside className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div><h2 className="font-semibold text-slate-900">Node types</h2><div className="mt-3 space-y-3">{ALL_TYPES.map((type) => <label key={type} className="flex cursor-pointer items-center justify-between text-sm text-slate-700"><span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full" style={{ backgroundColor: COLORS[type] }} />{NAMES[type]}</span><input type="checkbox" checked={enabled.has(type)} onChange={() => toggle(type)} /></label>)}</div></div><div className="border-t border-slate-100 pt-5"><h2 className="font-semibold text-slate-900">Selected node</h2>{selected ? <dl className="mt-3 space-y-2 text-sm"><div><dt className="text-slate-400">Type</dt><dd className="font-medium capitalize">{selected.type}</dd></div><div><dt className="text-slate-400">Label</dt><dd className="break-words">{selected.label}</dd></div>{selected.year != null && <div><dt className="text-slate-400">Year</dt><dd>{selected.year}</dd></div>}{selected.citation_count != null && <div><dt className="text-slate-400">Citations</dt><dd>{selected.citation_count}</dd></div>}</dl> : <p className="mt-3 text-sm text-slate-500">Click a node to inspect it.</p>}</div><p className="flex gap-2 border-t border-slate-100 pt-5 text-xs text-slate-500"><Info className="h-4 w-4 shrink-0" />This view uses the same JSON as the Graph export.</p></aside></div>}</main></div>;
}
