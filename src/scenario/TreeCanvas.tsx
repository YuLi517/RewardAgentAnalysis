// src/scenario/TreeCanvas.tsx
// v1.0.2: 树形图 Canvas 2D 渲染 (L0-L3 共 29 节点)
import { useEffect, useRef } from 'react';

const COLORS = {
  bg: '#0a0a14', line: '#5AA4AE', root: '#5AA4AE',
  region1: '#5AA4AE', region2: '#C0EBD7', region3: '#F0C239', region4: '#758A99',
  leaf: '#3a3a4e', text: '#fff',
};

interface Node { x: number; y: number; r: number; label: string; }

const TREE = (() => {
  const root: Node = { x: 0.5, y: 0.10, r: 14, label: '0' };
  const l1: Node[] = [
    { x: 0.18, y: 0.30, r: 10, label: '1' },
    { x: 0.38, y: 0.30, r: 10, label: '2' },
    { x: 0.62, y: 0.30, r: 10, label: '3' },
    { x: 0.82, y: 0.30, r: 10, label: '4' },
  ];
  const l2: Node[] = [];
  l1.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      l2.push({ x: p.x - 0.04 + j * 0.08, y: 0.55, r: 7, label: `${i + 1}.${j + 1}` });
    }
  });
  const l3: Node[] = [];
  l2.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      l3.push({ x: p.x - 0.025 + j * 0.05, y: 0.82, r: 5, label: '' });
    }
  });
  return { root, l1, l2, l3 };
})();

function drawNode(ctx: CanvasRenderingContext2D, n: Node, w: number, h: number, color: string) {
  const x = n.x * w, y = n.y * h;
  ctx.beginPath();
  ctx.arc(x, y, n.r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  if (n.label) {
    ctx.fillStyle = COLORS.text;
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(n.label, x, y + 3);
  }
}

function drawLine(ctx: CanvasRenderingContext2D, a: Node, b: Node, w: number, h: number) {
  ctx.beginPath();
  ctx.moveTo(a.x * w, a.y * h);
  ctx.lineTo(b.x * w, b.y * h);
  ctx.strokeStyle = COLORS.line;
  ctx.globalAlpha = 0.4;
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.globalAlpha = 1;
}

interface TreeCanvasProps {
  totalNodes?: number;
}

export function TreeCanvas({ totalNodes = 2144 }: TreeCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // L0 -> L1
    TREE.l1.forEach((c) => drawLine(ctx, TREE.root, c, w, h));
    // L1 -> L2
    TREE.l1.forEach((p, i) => {
      TREE.l2.slice(i * 2, i * 2 + 2).forEach((c) => drawLine(ctx, p, c, w, h));
    });
    // L2 -> L3
    TREE.l2.forEach((p, i) => {
      TREE.l3.slice(i * 2, i * 2 + 2).forEach((c) => drawLine(ctx, p, c, w, h));
    });

    drawNode(ctx, TREE.root, w, h, COLORS.root);
    TREE.l1.forEach((c, i) => drawNode(ctx, c, w, h, COLORS[`region${i + 1}` as keyof typeof COLORS]));
    TREE.l2.forEach((c) => drawNode(ctx, c, w, h, COLORS.leaf));
    TREE.l3.forEach((c) => drawNode(ctx, c, w, h, COLORS.leaf));
  }, []);

  return (
    <div className="canvas-wrap">
      <canvas ref={canvasRef} id="tree-canvas" width={600} height={280} />
      <p className="canvas-hint">省略 L4+, 共 {totalNodes} 节点</p>
    </div>
  );
}
