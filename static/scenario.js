// static/scenario.js (完整实现)
(function() {
  'use strict';

  const COLORS = {
    bg: '#0a0a14', line: '#5AA4AE', root: '#5AA4AE',
    region1: '#5AA4AE', region2: '#C0EBD7', region3: '#F0C239', region4: '#758A99',
    leaf: '#3a3a4e', text: '#fff',
  };

  const TREE = {
    // 1 + 4 + 8 + 16 = 29 节点 (L0-L3)
    root: { x: 0.5, y: 0.10, r: 14, label: '0' },
    l1: [
      { x: 0.18, y: 0.30, r: 10, label: '1' },
      { x: 0.38, y: 0.30, r: 10, label: '2' },
      { x: 0.62, y: 0.30, r: 10, label: '3' },
      { x: 0.82, y: 0.30, r: 10, label: '4' },
    ],
    l2: [], // 8 节点, 4 L1 各 2 子
    l3: [], // 16 节点, 8 L2 各 2 子
  };

  // 生成 L2/L3 坐标
  TREE.l1.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      TREE.l2.push({ x: p.x - 0.04 + j * 0.08, y: 0.55, r: 7, label: `${i+1}.${j+1}` });
    }
  });
  TREE.l2.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      TREE.l3.push({ x: p.x - 0.025 + j * 0.05, y: 0.82, r: 5, label: '' });
    }
  });

  function drawNode(ctx, node, w, h, color) {
    const x = node.x * w, y = node.y * h;
    ctx.beginPath();
    ctx.arc(x, y, node.r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    if (node.label) {
      ctx.fillStyle = COLORS.text;
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(node.label, x, y + 3);
    }
  }
  function drawLine(ctx, n1, n2, w, h) {
    ctx.beginPath();
    ctx.moveTo(n1.x * w, n1.y * h);
    ctx.lineTo(n2.x * w, n2.y * h);
    ctx.strokeStyle = COLORS.line;
    ctx.globalAlpha = 0.4;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function renderTree() {
    const canvas = document.getElementById('tree-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // L0 -> L1 连线
    TREE.l1.forEach(c => drawLine(ctx, TREE.root, c, w, h));
    // L1 -> L2 连线
    TREE.l1.forEach((p, i) => {
      TREE.l2.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });
    // L2 -> L3 连线
    TREE.l2.forEach((p, i) => {
      TREE.l3.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });

    // 画节点
    drawNode(ctx, TREE.root, w, h, COLORS.root);
    TREE.l1.forEach((c, i) => drawNode(ctx, c, w, h, COLORS[`region${i+1}`]));
    TREE.l2.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
    TREE.l3.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
  }

  // 文档加载后立即画
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderTree);
  } else {
    renderTree();
  }

  // 公开 API
  window.P3_renderTree = renderTree;
})();
