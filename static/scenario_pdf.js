// static/scenario_pdf.js (P5 商业计划书 PDF 导出 — 6 段流程)
(function() {
  'use strict';

  // === 配色 (复 P3 PR1 + 8 报酬业务分色) ===
  const COLORS = {
    bg: '#0a0a14',
    line: '#5AA4AE',
    root: '#5AA4AE',
    region1: '#5AA4AE',
    region2: '#C0EBD7',
    region3: '#F0C239',
    region4: '#758A99',
    leaf: '#3a3a4e',
    text: '#fff',
  };

  // 8 报酬固定顺序 (跟 /api/scenarios/{id}/overview 返 camelCase 一致)
  const REWARD_FIELDS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                         'leader', 'horizontal', 'retail', 'total'];
  // 业务分色 (ownBasic 主色, pairBonus 辅色, teamBonus 金, savings 浅色,
  //  leader/horizontal/retail 透明版, total 高亮主色)
  const REWARD_COLORS = ['#5AA4AE', '#758A99', '#F0C239', '#C0EBD7',
                         '#5AA4AE80', '#758A9980', '#C0EBD780', '#5AA4AE'];
  const REWARD_LABELS = {
    ownBasic: 'ownBasic (基本佣金)',
    pairBonus: 'pairBonus (对等奖金 7代)',
    teamBonus: 'teamBonus (团队培育 4档)',
    savings: 'savings (储蓄 15%)',
    leader: 'leader (领导分红)',
    horizontal: 'horizontal (横向领导)',
    retail: 'retail (零售利润)',
    total: 'total (合计)',
  };

  // TOP 5 节点: 业务接受固定抽样 bfs_id=0/1/2/3/4 (root + L1 大区, 5min 业务接受)
  const TOP5_BFS_IDS = [0, 1, 2, 3, 4];
  const TOTAL_MONTHS = 14;

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  let allScenarios = [];     // [{id, name, created_at, total_target, ...}]
  let currentId = null;
  let currentData = null;    // {stateM14, overviewM14, overviewAll, top5: []}

  // ============================================================
  // 工具函数 (复 P3 PR1 + PR2 + PR3 + P4)
  // ============================================================

  function showToast(msg, type) {
    const t = $('#toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'pdf-toast ' + (type || 'info');
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatUSD(s) {
    const n = parseFloat(s);
    if (isNaN(n) || n === 0) return '$0.00';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // state 端点返 snake_case 字段, 转 camelCase
  function stateToRewardMap(state) {
    if (!state) return {};
    return {
      ownBasic: state.own_basic_usd || '0',
      pairBonus: state.pair_bonus_usd || '0',
      teamBonus: state.team_bonus_usd || '0',
      savings: state.savings_usd || '0',
      leader: state.leader_dividend_usd || '0',
      horizontal: state.horizontal_leader_usd || '0',
      retail: state.retail_profit_usd || '0',
      total: state.total_usd || '0',
    };
  }

  // ============================================================
  // 树形: 复 P3 PR1 drawNode / drawLine (1 + 4 + 8 + 16 = 29 节点)
  // ============================================================

  const TREE = {
    root: { x: 0.5, y: 0.10, r: 14, label: '0' },
    l1: [
      { x: 0.18, y: 0.30, r: 10, label: '1' },
      { x: 0.38, y: 0.30, r: 10, label: '2' },
      { x: 0.62, y: 0.30, r: 10, label: '3' },
      { x: 0.82, y: 0.30, r: 10, label: '4' },
    ],
    l2: [],
    l3: [],
  };
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

  function renderTreeCanvas() {
    const canvas = $('#section-tree-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);
    TREE.l1.forEach(c => drawLine(ctx, TREE.root, c, w, h));
    TREE.l1.forEach((p, i) => {
      TREE.l2.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });
    TREE.l2.forEach((p, i) => {
      TREE.l3.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });
    drawNode(ctx, TREE.root, w, h, COLORS.root);
    TREE.l1.forEach((c, i) => drawNode(ctx, c, w, h, COLORS[`region${i+1}`]));
    TREE.l2.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
    TREE.l3.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
  }

  // ============================================================
  // 热图: 复 PR2 业务分色
  // ============================================================

  const HEATMAP_LABEL_W = 80, HEATMAP_LABEL_H = 22;
  const HEATMAP_CELL_W = 36, HEATMAP_CELL_H = 22, HEATMAP_GAP = 3;

  function hexToRgba(hex, alpha) {
    if (hex.length === 9) hex = hex.slice(0, 7);
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function renderHeatmap(overviewAll) {
    const canvas = $('#section-heatmap-canvas');
    if (!canvas || !overviewAll) return;
    const ctx = canvas.getContext('2d');
    const totalCols = overviewAll.months.length;
    const totalRows = REWARD_FIELDS.length;
    canvas.width = HEATMAP_LABEL_W + totalCols * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_GAP;
    canvas.height = HEATMAP_LABEL_H + totalRows * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_GAP;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // 行 label
    ctx.fillStyle = '#758A99';
    ctx.font = '10px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    REWARD_FIELDS.forEach((f, i) => {
      const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_CELL_H / 2;
      ctx.fillText(f, HEATMAP_LABEL_W - 6, y);
    });
    // 列 label
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    overviewAll.months.forEach((m, j) => {
      const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_CELL_W / 2;
      ctx.fillText('M' + m, x, HEATMAP_LABEL_H - 4);
    });

    // 单元格 (alpha 按行 max 缩放)
    REWARD_FIELDS.forEach((f, i) => {
      const rowValues = overviewAll.matrix[f].map(v => parseFloat(v) || 0);
      const maxV = Math.max(...rowValues, 0.01);
      rowValues.forEach((v, j) => {
        const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP);
        const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP);
        const alpha = Math.min(1.0, Math.max(0.1, v / maxV));
        ctx.fillStyle = hexToRgba(REWARD_COLORS[i], alpha);
        ctx.fillRect(x, y, HEATMAP_CELL_W, HEATMAP_CELL_H);
        // 月份数值 (避免太挤, 跳过 m=0)
        if (j > 0) {
          ctx.fillStyle = alpha > 0.5 ? '#fff' : '#333';
          ctx.font = '8px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('$' + Math.round(v), x + HEATMAP_CELL_W / 2, y + HEATMAP_CELL_H / 2);
        }
      });
    });
  }

  // ============================================================
  // 14 月 8 折线 (复 PR3, 拆 2 个 canvas: top 4 字段 + bot 4 字段)
  // ============================================================

  function renderLineChart(overviewAll, canvasId, fieldIndices) {
    const canvas = $(canvasId);
    if (!canvas || !overviewAll) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    const subW = W / Math.min(fieldIndices.length, 4);
    const padL = 60, padB = 28, padT = 28, padR = 14;
    const colors = REWARD_COLORS;
    const months = overviewAll.months;

    fieldIndices.forEach((fIdx, plotIdx) => {
      const f = REWARD_FIELDS[fIdx];
      const col = plotIdx % 4;
      const x0 = col * subW;
      const y0 = 0;
      const plotW = subW - padL - padR;
      const plotH = H - padT - padB;

      // 边框
      ctx.strokeStyle = '#2a2a3e';
      ctx.lineWidth = 1;
      ctx.strokeRect(x0 + padL, y0 + padT, plotW, plotH);

      // title
      ctx.fillStyle = colors[fIdx];
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(f, x0 + padL, y0 + 14);

      // y max
      let maxV = 0;
      months.forEach(m => {
        maxV = Math.max(maxV, parseFloat(overviewAll.matrix[f][m]) || 0);
      });
      if (maxV === 0) maxV = 1;

      // y 轴 labels (3 档)
      ctx.fillStyle = '#758A99';
      ctx.font = '9px monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      [0, 0.5, 1].forEach(t => {
        const y = y0 + padT + plotH - t * plotH;
        ctx.fillText('$' + Math.round(maxV * t), x0 + padL - 4, y);
      });

      // x 轴 labels
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      months.forEach((m, j) => {
        if (j % 2 !== 0 && j !== months.length - 1) return;
        const x = x0 + padL + (m / TOTAL_MONTHS) * plotW;
        ctx.fillText('M' + m, x, y0 + padT + plotH + 4);
      });

      // 0 折线
      ctx.strokeStyle = '#3a3a4e';
      ctx.beginPath();
      ctx.moveTo(x0 + padL, y0 + padT + plotH);
      ctx.lineTo(x0 + padL + plotW, y0 + padT + plotH);
      ctx.stroke();

      // 数据折线
      ctx.strokeStyle = colors[fIdx];
      ctx.lineWidth = 2;
      ctx.beginPath();
      months.forEach((m, j) => {
        const v = parseFloat(overviewAll.matrix[f][m]) || 0;
        const x = x0 + padL + (m / TOTAL_MONTHS) * plotW;
        const y = y0 + padT + plotH - (v / maxV) * plotH;
        if (j === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      // 节点圆点
      ctx.fillStyle = colors[fIdx];
      months.forEach((m, j) => {
        const v = parseFloat(overviewAll.matrix[f][m]) || 0;
        const x = x0 + padL + (m / TOTAL_MONTHS) * plotW;
        const y = y0 + padT + plotH - (v / maxV) * plotH;
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fill();
      });
    });
  }

  // ============================================================
  // TOP 5 横向条形 (新增)
  // ============================================================

  function renderTop5Bar(top5Data) {
    const canvas = $('#section-top5-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, W, H);

    if (!top5Data || top5Data.length === 0) {
      ctx.fillStyle = '#758A99';
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('暂无 TOP 5 数据', W / 2, H / 2);
      return;
    }

    const padL = 80, padR = 100, padT = 18, padB = 18;
    const plotW = W - padL - padR;
    const plotH = H - padT - padB;
    const n = top5Data.length;
    const barH = Math.min(28, plotH / n - 4);

    // 算 max
    let maxV = 0;
    top5Data.forEach(d => {
      const v = parseFloat(d.total) || 0;
      maxV = Math.max(maxV, v);
    });
    if (maxV === 0) maxV = 1;

    top5Data.forEach((d, i) => {
      const y = padT + i * (plotH / n) + (plotH / n - barH) / 2;
      const v = parseFloat(d.total) || 0;
      const barW = (v / maxV) * plotW;

      // label (左侧 bfs_id)
      ctx.fillStyle = '#758A99';
      ctx.font = 'bold 11px monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(`bfs_id=${d.bfs_id}`, padL - 8, y + barH / 2);

      // bar
      ctx.fillStyle = REWARD_COLORS[7];  // total 高亮主色
      ctx.fillRect(padL, y, Math.max(barW, 2), barH);

      // 数值
      ctx.fillStyle = COLORS.text;
      ctx.font = '11px monospace';
      ctx.textAlign = 'left';
      ctx.fillText(formatUSD(v), padL + barW + 8, y + barH / 2);
    });
  }

  // ============================================================
  // 9 section 渲染 (按 spec §4)
  // ============================================================

  function renderCover() {
    const s = allScenarios.find(x => x.id === currentId);
    const today = new Date().toISOString().slice(0, 10);
    $('#cover-title').textContent = `Scenario ${currentId}: ${s ? s.name : '—'}`;
    $('#cover-meta').textContent = `生成日期: ${today} | 节点总数: ${s ? s.total_target : '—'} | 月份范围: M0-M${TOTAL_MONTHS}`;
  }

  function renderSummaryCards(state) {
    const rewardMap = stateToRewardMap(state);
    $$('#summary-cards .glow-card').forEach(card => {
      const f = card.dataset.field;
      if (rewardMap[f] !== undefined) {
        card.querySelector('.val').textContent = formatUSD(rewardMap[f]);
      }
    });
    // 月均
    const total = parseFloat(rewardMap.total) || 0;
    $('#summary-avg').textContent = formatUSD(total / 14);
  }

  function renderParams(s) {
    if (!s) return;
    $('#p-fork').textContent = s.tree_shape ? s.tree_shape.fork_type : '—';
    $('#p-maxlv').textContent = s.tree_shape ? s.tree_shape.max_level : '—';
    $('#p-target').textContent = s.total_target || '—';
    $('#p-perweek').textContent = s.growth ? s.growth.nodes_per_region_per_week : '—';
    $('#p-nreg').textContent = s.growth ? s.growth.n_regions : '—';
    $('#p-wkmon').textContent = s.growth ? s.growth.weeks_per_month : '—';
    $('#p-pv').textContent = s.revenue ? s.revenue.initial_pv : '—';
    $('#p-renew').textContent = s.revenue ? s.revenue.monthly_renew_pv : '—';
    $('#p-rate').textContent = s.commission_config
      ? Math.round(s.commission_config.own_basic_rate * 100) + '%'
      : '—';
  }

  function renderTop5Cards(top5Data) {
    const container = $('#top5-cards');
    if (!container) return;
    container.innerHTML = '';
    if (!top5Data || top5Data.length === 0) {
      container.innerHTML = '<p style="color:#758A99;font-size:12px">暂无 TOP 5 节点数据</p>';
      return;
    }
    top5Data.forEach(d => {
      const card = document.createElement('div');
      card.className = 'glow-card glow-card-compact';
      const totalVal = formatUSD(d.total);
      card.innerHTML = `
        <div class="label">bfs_id=${d.bfs_id} ${d.bfs_id === 0 ? '(root 王常军)' : ''}</div>
        <div class="val" style="color:#5AA4AE">total: ${totalVal}</div>
      `;
      container.appendChild(card);
    });
  }

  // ============================================================
  // 侧栏 + 列表
  // ============================================================

  async function loadList() {
    try {
      const resp = await fetch('/api/scenarios');
      if (!resp.ok) {
        $('#scenario-list').innerHTML = '<p style="color:#EF4444;font-size:12px">加载失败: HTTP ' + resp.status + '</p>';
        return;
      }
      const text = await resp.text();
      const lines = text.trim().split('\n');
      allScenarios = lines.slice(1).map(line => {
        const parts = line.split(',');
        return {
          id: parseInt(parts[0]),
          name: parts[1],
          created_at: parts[2],
          total_target: parseInt(parts[3]),
          total_weeks: parseInt(parts[4]),
          total_months: parseInt(parts[5]),
        };
      });
      renderList();
    } catch (err) {
      $('#scenario-list').innerHTML = '<p style="color:#EF4444;font-size:12px">网络错误: ' + err.message + '</p>';
    }
  }

  function renderList() {
    const list = $('#scenario-list');
    if (allScenarios.length === 0) {
      list.innerHTML = '<p style="color:#758A99;font-size:12px">暂无 scenario, 去 <a href="/static/scenario.html" style="color:#5AA4AE">scenario.html</a> 创建</p>';
      return;
    }
    list.innerHTML = '';
    allScenarios.forEach(s => {
      const item = document.createElement('div');
      item.className = 'pdf-sidebar-item' + (s.id === currentId ? ' active' : '');
      item.dataset.id = s.id;
      item.innerHTML = `
        <div><strong>S${s.id}:</strong> ${s.name}</div>
        <span class="meta">📅 ${(s.created_at || '').slice(0, 16)} | M${s.total_months} (${s.total_target} 节点)</span>
      `;
      item.addEventListener('click', () => selectScenario(s.id));
      list.appendChild(item);
    });
  }

  // ============================================================
  // 6 段流程 Step 2: 用户点 scenario → 拉数据 → 渲染
  // ============================================================

  async function selectScenario(id) {
    currentId = id;
    renderList();  // 高亮 active

    showToast(`加载 S${id} 数据...`, 'info');
    const t0 = Date.now();

    try {
      // 1) state M14 bfs_id=0 (root 当月 8 报酬 + 累计)
      const stateResp = await fetch(`/api/scenarios/${id}/state?month=14&bfs_id=0`);
      if (!stateResp.ok) throw new Error('state HTTP ' + stateResp.status);
      const stateM14 = await stateResp.json();

      // 2) overview/all 14 月 × 8 报酬矩阵 (曲线 + 热图)
      const allResp = await fetch(`/api/scenarios/${id}/overview/all?total_months=${TOTAL_MONTHS}`);
      if (!allResp.ok) throw new Error('overview/all HTTP ' + allResp.status);
      const overviewAll = await allResp.json();

      // 3) TOP 5 节点 (业务接受 bfs_id=0/1/2/3/4 固定抽样, 5×60s=5min)
      const top5Data = [];
      top5Data.push({ bfs_id: 0, ...stateToRewardMap(stateM14) });
      for (let i = 1; i < TOP5_BFS_IDS.length; i++) {
        const bfsId = TOP5_BFS_IDS[i];
        showToast(`拉取 TOP 5 节点 ${i+1}/${TOP5_BFS_IDS.length} (bfs_id=${bfsId})...`, 'info');
        try {
          const r = await fetch(`/api/scenarios/${id}/state?month=14&bfs_id=${bfsId}`);
          if (r.ok) {
            const st = await r.json();
            top5Data.push({ bfs_id: bfsId, ...stateToRewardMap(st) });
          } else {
            // 部分大区可能空, 推 0 占位
            top5Data.push({ bfs_id: bfsId, total: '0' });
          }
        } catch (e) {
          top5Data.push({ bfs_id: bfsId, total: '0' });
        }
      }

      currentData = { stateM14, overviewAll, top5Data };
      const elapsed = ((Date.now() - t0) / 1000).toFixed(1);

      // 4) 渲染 9 section
      renderCover();
      renderSummaryCards(stateM14);
      renderTreeCanvas();
      renderParams(allScenarios.find(x => x.id === id));
      // Section 5-6: 14 月 8 折线 (top 4 字段 + bot 4 字段)
      renderLineChart(overviewAll, '#section-line-canvas-top', [0, 1, 2, 3]);
      renderLineChart(overviewAll, '#section-line-canvas-bot', [4, 5, 6, 7]);
      renderHeatmap(overviewAll);
      renderTop5Bar(top5Data);
      renderTop5Cards(top5Data);
      // Section 9 风险免责 + 签字: 静态 HTML 已写, 无 JS 渲染

      showToast(`✅ S${id} 渲染完成 (${elapsed}s)`, 'success');
    } catch (err) {
      showToast('❌ 加载失败: ' + err.message, 'error');
      console.error(err);
    }
  }

  // ============================================================
  // 6 段流程 Step 4-6: html2canvas 截图 + jsPDF 拼 9 页
  // ============================================================

  async function generatePDF() {
    if (!currentId) {
      showToast('先选 1 个 scenario', 'error');
      return;
    }
    if (typeof window.jspdf === 'undefined' || typeof html2canvas === 'undefined') {
      showToast('❌ jsPDF / html2canvas CDN 加载失败, 检查网络', 'error');
      return;
    }
    if (!currentData) {
      showToast('数据还没加载完, 等下', 'error');
      return;
    }

    const btn = $('#btn-generate-pdf');
    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = '⏳ 生成中...';

    const sections = $$('.pdf-section');
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF('p', 'mm', 'a4');

    try {
      for (let i = 0; i < sections.length; i++) {
        showToast(`正在生成第 ${i+1}/${sections.length} 页...`, 'info');
        // 强制 section 可见 (避免被 sidebar sticky 遮挡)
        sections[i].style.display = 'block';

        const canvas = await html2canvas(sections[i], {
          scale: 2,
          backgroundColor: '#ffffff',
          logging: false,
          useCORS: true,
        });
        const imgData = canvas.toDataURL('image/jpeg', 0.95);
        const imgWidth = 210;  // A4 宽 mm
        const pageHeight = 297;  // A4 高 mm
        const imgHeight = (canvas.height * imgWidth) / canvas.width;
        if (i > 0) pdf.addPage();
        pdf.addImage(imgData, 'JPEG', 0, 0, imgWidth, Math.min(imgHeight, pageHeight));
        // 短暂等待让 UI 更新 (避免浏览器卡死)
        await new Promise(r => setTimeout(r, 50));
      }
      const today = new Date().toISOString().slice(0, 10);
      const s = allScenarios.find(x => x.id === currentId);
      const fname = `scenario_${currentId}_${s ? s.name : 'plan'}_${today}.pdf`;
      pdf.save(fname);
      showToast(`✅ PDF 已下载: ${fname}`, 'success');
    } catch (err) {
      showToast('❌ PDF 生成失败: ' + err.message, 'error');
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  }

  // ============================================================
  // DOMContentLoaded 启动
  // ============================================================

  document.addEventListener('DOMContentLoaded', () => {
    loadList();
    $('#btn-generate-pdf').addEventListener('click', generatePDF);
  });
})();
