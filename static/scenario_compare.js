(function() {
  'use strict';

  const FIELDS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                  'leader', 'horizontal', 'oneGenFour', 'total'];
  // v1.0.15: retail 卡片改 1代4 产品奖金 (oneGenFour), 9→8 字段
  const SCENARIO_COLORS = [
    { ownBasic: '#5AA4AE', pairBonus: '#758A99', teamBonus: '#F0C239', savings: '#C0EBD7',
      leader: '#5AA4AE', horizontal: '#758A99', oneGenFour: '#F0C23980', total: '#5AA4AE' },
    { ownBasic: '#5AA4AE80', pairBonus: '#758A9980', teamBonus: '#F0C23980', savings: '#C0EBD780',
      leader: '#5AA4AE80', horizontal: '#758A9980', oneGenFour: '#F0C23980', total: '#5AA4AE80' },
    { ownBasic: '#5AA4AECC', pairBonus: '#758A99CC', teamBonus: '#F0C239CC', savings: '#C0EBD7CC',
      leader: '#5AA4AECC', horizontal: '#758A99CC', oneGenFour: '#F0C239CC', total: '#5AA4AECC' },
    { ownBasic: '#5AA4AEFF', pairBonus: '#758A99FF', teamBonus: '#F0C239FF', savings: '#C0EBD7FF',
      leader: '#5AA4AEFF', horizontal: '#758A99FF', oneGenFour: '#F0C239FF', total: '#5AA4AEFF' },
  ];
  const MAX_SELECTED = 4;
  const TOTAL_MONTHS = 14;

  let allScenarios = [];   // [{id, name, total_target, ...}]
  let selectedIds = [];   // [1, 3, 5]
  let allData = {};       // {scenario_id: {fields: [...], months: [...], matrix: {field: [v0, v1, ...]}}}

  const $ = (s) => document.querySelector(s);

  async function loadList() {
    const resp = await fetch('/api/scenarios');
    if (!resp.ok) return;
    const text = await resp.text();
    const lines = text.trim().split('\n');
    allScenarios = lines.slice(1).map(line => {
      const [id, name, created_at, total_target, total_weeks, total_months] = line.split(',');
      return { id: parseInt(id), name, created_at, total_target: parseInt(total_target),
               total_weeks: parseInt(total_weeks), total_months: parseInt(total_months) };
    });
    renderList();
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
      item.className = 'scenario-item';
      const checked = selectedIds.includes(s.id);
      item.innerHTML = `
        <input type="checkbox" data-id="${s.id}" ${checked ? 'checked' : ''}>
        <label>S${s.id}: ${s.name}</label>
        <span class="meta">M${s.total_months} (${s.total_target})</span>
      `;
      list.appendChild(item);
    });
    list.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.addEventListener('change', onCheckboxChange);
    });
  }

  async function onCheckboxChange(e) {
    const id = parseInt(e.target.dataset.id);
    if (e.target.checked) {
      if (selectedIds.length >= MAX_SELECTED) {
        e.target.checked = false;
        alert(`最多选 ${MAX_SELECTED} 个 scenario`);
        return;
      }
      selectedIds.push(id);
      // 拉数据
      if (!allData[id]) {
        const resp = await fetch(`/api/scenarios/${id}/overview/all?total_months=${TOTAL_MONTHS}`);
        if (resp.ok) {
          allData[id] = await resp.json();
        }
      }
    } else {
      selectedIds = selectedIds.filter(x => x !== id);
    }
    renderPlots();
  }

  function renderPlots() {
    const canvas = $('#plot-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = 900;
    const H = canvas.height = 500;  // v1.0.15: 8 subplot 2 行 4 列, 高度回到 500
    ctx.fillStyle = '#0a0a14';
    ctx.fillRect(0, 0, W, H);

    if (selectedIds.length === 0) {
      ctx.fillStyle = '#758A99';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('选 2-4 个 scenario 看 8 报酬 折线对比', W / 2, H / 2);
      return;
    }

    // 8 subplot 2 行 4 列 (v1.0.15: retail 卡片改 1代4 产品奖金, 9→8)
    const subW = W / 4, subH = H / 2;
    const padL = 50, padB = 20, padT = 30, padR = 10;
    FIELDS.forEach((f, idx) => {
      const col = idx % 4, row = Math.floor(idx / 4);
      const x0 = col * subW, y0 = row * subH;
      const plotW = subW - padL - padR, plotH = subH - padT - padB;

      // 边框
      ctx.strokeStyle = '#2a2a3e';
      ctx.lineWidth = 1;
      ctx.strokeRect(x0 + padL, y0 + padT, plotW, plotH);

      // title
      ctx.fillStyle = '#5AA4AE';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(f, x0 + padL, y0 + 15);

      // 算 y 轴 max (跨所有选中 scenarios)
      let maxV = 0;
      selectedIds.forEach(sid => {
        if (allData[sid]) {
          allData[sid].matrix[f].forEach(v => { maxV = Math.max(maxV, parseFloat(v) || 0); });
        }
      });
      if (maxV === 0) maxV = 1;

      // 画 0 折线
      ctx.strokeStyle = '#3a3a4e';
      ctx.beginPath();
      ctx.moveTo(x0 + padL, y0 + padT + plotH);
      ctx.lineTo(x0 + padL + plotW, y0 + padT + plotH);
      ctx.stroke();

      // 每个 scenario 1 折线
      selectedIds.forEach((sid, sIdx) => {
        if (!allData[sid]) return;
        const colorSet = SCENARIO_COLORS[sIdx % SCENARIO_COLORS.length];
        ctx.strokeStyle = colorSet[f];
        ctx.lineWidth = 2;
        ctx.beginPath();
        const months = allData[sid].months;
        const values = allData[sid].matrix[f];
        months.forEach((m, j) => {
          const x = x0 + padL + (m / TOTAL_MONTHS) * plotW;
          const y = y0 + padT + plotH - (parseFloat(values[j]) / maxV) * plotH;
          if (j === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // legend dot
        ctx.fillStyle = colorSet[f];
        ctx.beginPath();
        ctx.arc(x0 + padL + plotW - 80 + sIdx * 18, y0 + 15, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#758A99';
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('S' + sid, x0 + padL + plotW - 70 + sIdx * 18, y0 + 19);
      });
    });
  }

  function exportPNG() {
    const canvas = $('#plot-canvas');
    if (!canvas) return;
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `scenario_compare_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  async function exportCSV() {
    if (selectedIds.length === 0) {
      alert('先选 1 个 scenario (单 scenario CSV 导出)');
      return;
    }
    const sid = selectedIds[0];
    const resp = await fetch(`/api/scenarios/${sid}/export/csv?total_months=${TOTAL_MONTHS}`);
    if (!resp.ok) { alert('CSV 导出失败: ' + resp.status); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `scenario_${sid}_overview.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadList();
    $('#btn-export-png').addEventListener('click', exportPNG);
    $('#btn-export-csv').addEventListener('click', exportCSV);
  });
})();
