// static/scenario_library.js
(function() {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  let allScenarios = [];  // [{id, name, created_at, total_target, ...}]
  let currentId = null;   // URL ?id=123 解析的 id

  function showToast(msg, type) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'lib-toast ' + type;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatUSD(s) {
    const n = parseFloat(s);
    if (isNaN(n)) return '$0.00';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

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
      item.className = 'lib-scenario-item' + (s.id === currentId ? ' active' : '');
      item.dataset.id = s.id;
      item.innerHTML = `
        <div><strong>S${s.id}:</strong> ${s.name}</div>
        <div class="meta">📅 ${(s.created_at || '').slice(0, 16)} | M${s.total_months} (${s.total_target} 节点)</div>
      `;
      item.addEventListener('click', () => selectScenario(s.id));
      list.appendChild(item);
    });
  }

  function selectScenario(id) {
    // 更新 URL (无 reload)
    const url = new URL(window.location.href);
    url.searchParams.set('id', id);
    window.history.pushState({}, '', url);
    currentId = id;
    renderList();  // 重新渲染侧栏 (高亮 active)
    loadDetail(id);
  }

  async function loadDetail(id) {
    const detail = $('#detail-section');
    detail.style.display = 'block';
    $('#detail-title').textContent = '📌 S' + id + ' 加载中...';
    $('#detail-meta').textContent = '';
    try {
      // 1) GET scenario 详情 (通过 repository.load 暂时不暴露, 用 list 拿 name + created_at)
      const s = allScenarios.find(x => x.id === id);
      if (s) {
        $('#detail-title').textContent = `📌 S${s.id}: ${s.name}`;
        $('#detail-meta').textContent = `📅 ${(s.created_at || '').slice(0, 19)} | M${s.total_months} (${s.total_target} 节点)`;
      }
      // 2) GET overview M14 (跟 PR1 一样, 拍板 bfs_id=0 展示根节点, 这里用 overview 拿 8 报酬)
      const ovResp = await fetch(`/api/scenarios/${id}/overview?month=14`);
      if (!ovResp.ok) throw new Error('overview HTTP ' + ovResp.status);
      const overview = await ovResp.json();
      const fields = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                      'leader', 'horizontal', 'retail', 'total'];
      $$('.lib-cards .card').forEach(card => {
        const f = card.dataset.field;
        if (overview[f] !== undefined) {
          card.querySelector('.val').textContent = formatUSD(overview[f]);
        }
      });
      // 3) GET state M14 bfs_id=0 拿 4 参数 (走 /state 端点返 12 字段, 从 to_dict 拿 4 参数)
      // 简化: P4 不展示 4 参数完整值, 只展示 8 报酬 (跟 spec 拍板一致)
      $('#p-fork').textContent = '-';
      $('#p-maxlv').textContent = '-';
      $('#p-target').textContent = s ? s.total_target : '-';
      $('#p-perweek').textContent = '-';
      $('#p-nreg').textContent = '-';
      $('#p-wkmon').textContent = '-';
      $('#p-pv').textContent = '-';
      $('#p-renew').textContent = '-';
      $('#p-rate').textContent = '-';
      // 4) 分享 URL
      const shareUrl = `${window.location.origin}/static/scenario_library.html?id=${id}`;
      $('#detail-url').textContent = '🔗 ' + shareUrl;
    } catch (err) {
      $('#detail-title').textContent = '❌ 加载失败: ' + err.message;
      showToast('加载失败: ' + err.message, 'error');
    }
  }

  function shareUrl() {
    if (!currentId) {
      showToast('先选 1 个 scenario', 'error');
      return;
    }
    const url = `${window.location.origin}/static/scenario_library.html?id=${currentId}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('✅ 链接已复制: ' + url, 'success');
      }).catch(() => {
        // Fallback: 提示用户手动复制
        prompt('复制下面链接:', url);
      });
    } else {
      prompt('复制下面链接:', url);
    }
  }

  function goCompare() {
    if (!currentId) {
      showToast('先选 1 个 scenario', 'error');
      return;
    }
    window.location.href = `/static/scenario_compare.html?ids=${currentId}`;
  }

  document.addEventListener('DOMContentLoaded', () => {
    // 读 URL ?id=123
    const params = new URLSearchParams(window.location.search);
    currentId = parseInt(params.get('id')) || null;
    loadList();
    if (currentId) loadDetail(currentId);
    $('#btn-share').addEventListener('click', shareUrl);
    $('#btn-compare').addEventListener('click', goCompare);
  });
})();
