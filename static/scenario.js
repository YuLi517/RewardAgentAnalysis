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

  // === formState (Task 1 恢复, Task 3 submitScenario 引用) ===
  const formState = {
    name: 'live_scenario',
    tree_shape: { fork_type: 'binary', max_level: 10,
                  layer_counts: {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99} },
    growth: { nodes_per_region_per_week: 9, n_regions: 4, join_strategy: 'round_robin', weeks_per_month: 4 },
    revenue: { initial_pv: 1500, monthly_renew_pv: 100, color_rule: '4_color_cycle', color_names: ['红', '紫', '青绿', '蓝'] },
    commission_config: {
      enable_retail_profit: false, enable_team_bonus: true,
      team_bonus_tier_rates: {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
      team_bonus_window_weeks: 4,
      enable_own_basic: true, own_basic_rate: 0.15, own_basic_line_pv_cap: 13334,
      enable_savings: true, savings_usd_threshold: 250.0, savings_rate: 0.15, savings_cap_usd: 500.0,
      enable_pair_bonus: true,
      pair_bonus_ratios: {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
      pair_bonus_4th_usd_threshold: 500.0, pair_bonus_5th_usd_threshold: 1000.0,
      enable_leader_dividend: true, leader_dividend_threshold_pv: 13334,
      leader_dividend_share_usd: 500.0, leader_dividend_tiers: {1: 2, 2: 4, 3: 6, 4: 8},
      enable_horizontal_leader: true, horizontal_leader_share_usd: 250.0,
      horizontal_leader_tiers: {1: 2, 2: 2, 3: 4, 4: 6},
      enable_opportunity_points: false,
    },
  };

  // === POST/GET API 集成 (Task 3) ===
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function showToast(msg, type) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'p3-toast ' + type;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatUSD(s) {
    // 服务端返 "1234.5678" (Decimal 序列化), 格式化为 "$1,234.57"
    const n = parseFloat(s);
    if (isNaN(n) || n === 0) return '$0.00';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function updateCards(state, overview) {
    // overview 8 字段 (跟 scenario_routes.py: get_overview 返的 dict 一致)
    const map = {
      ownBasic: overview.ownBasic,
      pairBonus: overview.pairBonus,
      teamBonus: overview.teamBonus,
      savings: overview.savings,
      leader: overview.leader,
      horizontal: overview.horizontal,
      retail: overview.retail,
      total: overview.total,
    };
    $$('.p3-cards .card').forEach(card => {
      const field = card.dataset.field;
      if (map[field] !== undefined) {
        card.querySelector('.val').textContent = formatUSD(map[field]);
      }
    });
  }

  async function submitScenario() {
    const btn = $('#btn-submit');
    btn.disabled = true;
    btn.textContent = '提交中...';

    // JSON 字段 key 转 str (Pydantic v2 Dict[str, int] 要求)
    const body = JSON.parse(JSON.stringify(formState));
    body.tree_shape.layer_counts = Object.fromEntries(
      Object.entries(body.tree_shape.layer_counts).map(([k, v]) => [String(k), v])
    );
    body.commission_config.team_bonus_tier_rates = Object.fromEntries(
      Object.entries(body.commission_config.team_bonus_tier_rates).map(([k, v]) => [String(k), v])
    );
    body.commission_config.pair_bonus_ratios = Object.fromEntries(
      Object.entries(body.commission_config.pair_bonus_ratios).map(([k, v]) => [String(k), v])
    );
    body.commission_config.leader_dividend_tiers = Object.fromEntries(
      Object.entries(body.commission_config.leader_dividend_tiers).map(([k, v]) => [String(k), v])
    );
    body.commission_config.horizontal_leader_tiers = Object.fromEntries(
      Object.entries(body.commission_config.horizontal_leader_tiers).map(([k, v]) => [String(k), v])
    );

    try {
      // 1) POST /api/scenarios
      const postResp = await fetch('/api/scenarios', {
        method: 'POST', headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify(body),
      });
      if (!postResp.ok) {
        const err = await postResp.json();
        showToast('提交失败: ' + (err.detail || postResp.status), 'error');
        return;
      }
      const { id: scenario_id } = await postResp.json();

      // 2) GET /api/scenarios/{id}/overview?month=14
      const ovResp = await fetch(`/api/scenarios/${scenario_id}/overview?month=14`);
      if (!ovResp.ok) {
        showToast('overview 失败: ' + ovResp.status, 'error');
        return;
      }
      const overview = await ovResp.json();

      // 3) 更新卡片
      updateCards(null, overview);
      showToast(`scenario ${scenario_id} 计算完成`, 'success');
    } catch (err) {
      showToast('网络错误: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎲 提交场景 + 算报酬';
    }
  }

  // 绑定按钮
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      $('#btn-submit').addEventListener('click', submitScenario);
    });
  } else {
    $('#btn-submit').addEventListener('click', submitScenario);
  }

  // 公开 API (formState + getFormState)
  window.P3 = {
    formState,
    getFormState() { return formState; },
    showToast,
  };
})();
