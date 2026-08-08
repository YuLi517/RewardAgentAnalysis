// static/scenario.js (完整实现)
// v1.0.10 (2026-08-08): 删除 hardcode 树形图 (Canvas 2D) — 装饰品, 跟实际算的 2144 节点脱节
(function() {
  'use strict';

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
    // overview 9 字段 (v1.0.12 加 oneGenFour, 跟 scenario_routes.py: get_overview 返的 dict 一致)
    const map = {
      ownBasic: overview.ownBasic,
      pairBonus: overview.pairBonus,
      teamBonus: overview.teamBonus,
      savings: overview.savings,
      leader: overview.leader,
      horizontal: overview.horizontal,
      retail: overview.retail,
      oneGenFour: overview.oneGenFour,
      total: overview.total,
    };
    $$('.p3-cards .glow-card').forEach(card => {
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

      // P3 PR2: 拉 overview/all, 渲染热图 (业务 14 月 × 60s = 14 分钟, 接受)
      const allResp = await fetch(`/api/scenarios/${scenario_id}/overview/all?total_months=14`);
      if (allResp.ok) {
        heatmapData = await allResp.json();
        renderHeatmap();
        bindHeatmapEvents(scenario_id);
      }

      showToast(`scenario ${scenario_id} 计算完成`, 'success');
    } catch (err) {
      showToast('网络错误: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎲 提交场景 + 算报酬';
    }
  }

  // === P1 v1.0.1: 4 个 beam-wrap 的 .val-input 双向绑定到 formState ===
  // 业务: 用户改 max_level/total_target/fork_type/3 个 growth/2 个 revenue/2 个 commission
  //       改后 formState 同步, 提交按钮 (submitScenario) 自动用最新值
  // 设计: 9 个数字 input + 1 个 select + 1 个 readonly (team_bonus 4 档, PV 阈值业务规则强不动)
  function rebuildLayerCounts(totalTarget, forkType) {
    // total_target 改变 → 重新按 fork_type 算 layer_counts
    // 业务: L0=1, L1=fork_type, L_k+ = L_k * fork_type, 最后层 leftover
    const base = forkType === 'binary' ? 2 : forkType === 'ternary' ? 3 : 4;
    const counts = {0: 1};
    let sum = 1;
    for (let lv = 1; lv <= 10; lv++) {
      const next = counts[lv - 1] * base;
      if (sum + next > totalTarget) {
        counts[lv] = totalTarget - sum;  // 最后一层 leftover
        return formState.tree_shape.layer_counts = counts;
      }
      counts[lv] = next;
      sum += next;
    }
    return formState.tree_shape.layer_counts = counts;
  }

  function syncInputToFormState(el) {
    const section = el.closest('.glow-card')?.dataset.section;
    const key = el.dataset.key;
    if (!section || !key) return false;
    let value = el.value;
    // select (fork_type) 直接用 string
    if (el.tagName === 'SELECT') {
      // 直接更新 fork_type
      if (section === 'tree' && key === 'fork_type') {
        formState.tree_shape.fork_type = value;
        // fork_type 改变时, 按当前 total_target 重建 layer_counts
        const total = formState.tree_shape.layer_counts ? Object.values(formState.tree_shape.layer_counts).reduce((a, b) => a + b, 0) : 2144;
        rebuildLayerCounts(total, value);
      }
      return true;
    }
    // 数字 input (rate 用 float, 其余 int)
    const isFloat = /rate|ratio/.test(key);
    const num = isFloat ? parseFloat(value) : parseInt(value);
    if (isNaN(num) || num < 0) {
      el.classList.add('invalid');
      return false;
    }
    el.classList.remove('invalid');
    value = num;
    // 路径映射
    if (section === 'tree') {
      if (key === 'max_level') {
        // max_level 改变时裁剪 layer_counts 到 max_level
        const lc = formState.tree_shape.layer_counts || {};
        formState.tree_shape.max_level = value;
        formState.tree_shape.layer_counts = Object.fromEntries(
          Object.entries(lc).filter(([k]) => parseInt(k) <= value)
        );
      } else if (key === 'total_target') {
        rebuildLayerCounts(value, formState.tree_shape.fork_type);
      }
    } else if (section === 'growth') {
      formState.growth[key] = value;
    } else if (section === 'revenue') {
      formState.revenue[key] = value;
    } else if (section === 'commission') {
      if (key === 'own_basic_rate') {
        formState.commission_config.own_basic_rate = value;
      } else if (key === 'pair_bonus_ratio_1gen') {
        formState.commission_config.pair_bonus_ratios['1'] = value;
      }
    }
    return true;
  }

  function bindFormInputs() {
    document.querySelectorAll('.val-input').forEach(el => {
      el.addEventListener('input', () => syncInputToFormState(el));
      el.addEventListener('change', () => syncInputToFormState(el));
    });
  }

  // 绑定按钮 + 表单 input
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      $('#btn-submit').addEventListener('click', submitScenario);
      bindFormInputs();
    });
  } else {
    $('#btn-submit').addEventListener('click', submitScenario);
    bindFormInputs();
  }

  // === P3 PR2: 热图渲染 ===
  const HEATMAP_COLORS = {
    ownBasic: '#5AA4AE', pairBonus: '#758A99', teamBonus: '#F0C239',
    savings: '#C0EBD7', leader: '#5AA4AE80', horizontal: '#758A9980',
    retail: '#C0EBD780', oneGenFour: '#F0C23980', total: '#5AA4AE',
  };
  const HEATMAP_ROWS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                        'leader', 'horizontal', 'retail', 'oneGenFour', 'total'];
  const HEATMAP_CELL_W = 32, HEATMAP_CELL_H = 24, HEATMAP_GAP = 4;
  const HEATMAP_LABEL_W = 70, HEATMAP_LABEL_H = 20;
  let heatmapData = null;  // {fields, months, matrix}

  function hexToRgba(hex, alpha) {
    // hex = "#5AA4AE" or "#5AA4AE80" (带 alpha)
    if (hex.length === 9) hex = hex.slice(0, 7);
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function renderHeatmap() {
    if (!heatmapData) return;
    const canvas = document.getElementById('heatmap-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const totalCols = heatmapData.months.length;
    const totalRows = HEATMAP_ROWS.length;
    canvas.width = HEATMAP_LABEL_W + totalCols * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_GAP;
    canvas.height = HEATMAP_LABEL_H + totalRows * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_GAP;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#0a0a14';
    ctx.fillRect(0, 0, w, h);

    // 行 label (left)
    ctx.fillStyle = '#758A99';
    ctx.font = '11px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    HEATMAP_ROWS.forEach((f, i) => {
      const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_CELL_H / 2;
      ctx.fillText(f, HEATMAP_LABEL_W - 6, y);
    });
    // 列 label (top)
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    heatmapData.months.forEach((m, j) => {
      const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_CELL_W / 2;
      ctx.fillText('M' + m, x, HEATMAP_LABEL_H - 4);
    });

    // 算每行 max value (alpha 0.1-1.0 比例)
    HEATMAP_ROWS.forEach((f, i) => {
      const rowValues = heatmapData.matrix[f].map(v => parseFloat(v) || 0);
      const maxV = Math.max(...rowValues, 0.01);
      rowValues.forEach((v, j) => {
        const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP);
        const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP);
        const alpha = Math.min(1.0, Math.max(0.1, v / maxV));
        ctx.fillStyle = hexToRgba(HEATMAP_COLORS[f], alpha);
        ctx.fillRect(x, y, HEATMAP_CELL_W, HEATMAP_CELL_H);
      });
    });
    // 显示 heatmap section
    document.getElementById('heatmap').style.display = 'block';
  }

  function showHeatmapTooltip(event, row, col) {
    const tt = document.getElementById('heatmap-tooltip');
    if (!tt || !heatmapData) return;
    const f = HEATMAP_ROWS[row];
    const m = heatmapData.months[col];
    const v = heatmapData.matrix[f][m];
    tt.textContent = `${f}, M${m}, $${parseFloat(v).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    tt.style.display = 'block';
    tt.style.left = (event.clientX + 12) + 'px';
    tt.style.top = (event.clientY + 12) + 'px';
  }
  function hideHeatmapTooltip() {
    const tt = document.getElementById('heatmap-tooltip');
    if (tt) tt.style.display = 'none';
  }

  async function showMonthDetail(row, col, scenarioId) {
    if (!heatmapData) return;
    const detail = document.getElementById('month-detail');
    if (!detail) return;
    const m = heatmapData.months[col];
    detail.querySelector('.month-detail-body').innerHTML = '<p>加载中... (≤ 60s)</p>';
    detail.style.display = 'block';
    try {
      const resp = await fetch(`/api/scenarios/${scenarioId}/overview?month=${m}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const fields = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                      'leader', 'horizontal', 'retail', 'oneGenFour', 'total'];
      const body = detail.querySelector('.month-detail-body');
      body.innerHTML = '';
      const f = HEATMAP_ROWS[row];
      body.innerHTML += `<div class="field" style="grid-column: 1/-1; color:#5AA4AE">📅 M${m} (${f} 行: $${parseFloat(heatmapData.matrix[f][m]).toLocaleString('en-US', {minimumFractionDigits: 2})})</div>`;
      fields.forEach(field => {
        body.innerHTML += `<div class="field">${field}</div><div class="val">$${parseFloat(data[field] || '0').toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>`;
      });
    } catch (err) {
      detail.querySelector('.month-detail-body').innerHTML = '<p style="color:#EF4444">错误: ' + err.message + '</p>';
    }
  }
  function hideMonthDetail() {
    const detail = document.getElementById('month-detail');
    if (detail) detail.style.display = 'none';
  }

  function bindHeatmapEvents(scenarioId) {
    const canvas = document.getElementById('heatmap-canvas');
    if (!canvas) return;
    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < HEATMAP_LABEL_W || y < HEATMAP_LABEL_H) {
        hideHeatmapTooltip();
        return;
      }
      const j = Math.floor((x - HEATMAP_LABEL_W) / (HEATMAP_CELL_W + HEATMAP_GAP));
      const i = Math.floor((y - HEATMAP_LABEL_H) / (HEATMAP_CELL_H + HEATMAP_GAP));
      if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= heatmapData.months.length) {
        hideHeatmapTooltip();
        return;
      }
      showHeatmapTooltip(e, i, j);
    });
    canvas.addEventListener('mouseleave', hideHeatmapTooltip);
    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < HEATMAP_LABEL_W || y < HEATMAP_LABEL_H) return;
      const j = Math.floor((x - HEATMAP_LABEL_W) / (HEATMAP_CELL_W + HEATMAP_GAP));
      const i = Math.floor((y - HEATMAP_LABEL_H) / (HEATMAP_CELL_H + HEATMAP_GAP));
      if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= heatmapData.months.length) return;
      showMonthDetail(i, j, scenarioId);
    });
    document.querySelector('.month-detail-close').addEventListener('click', hideMonthDetail);
  }

  // 公开 API (formState + getFormState)
  window.P3 = {
    formState,
    getFormState() { return formState; },
    showToast,
  };
})();
