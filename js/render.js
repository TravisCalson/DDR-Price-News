// render.js — DOM rendering for all sections

function fmtPrice(v) {
  return v != null ? '$' + v.toFixed(2) : '—';
}

function fmtPct(v) {
  if (v == null) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

function pctClass(v) {
  if (v == null) return 'change-flat';
  if (v > 0) return 'change-up';
  if (v < 0) return 'change-down';
  return 'change-flat';
}

function confidenceBadge(level) {
  return `<span class="confidence-badge confidence-${level}">${level}</span>`;
}

// === KPI Cards ===
export function renderKPIs(container, priceData) {
  const highlights = [
    { id: 'ddr4_8gbit', label: 'DDR4 8Gb 现货' },
    { id: 'ddr5_16gbit', label: 'DDR5 16Gb 现货' },
    { id: 'ddr5_rdimm_32gb', label: 'DDR5 RDIMM 32GB' },
    { id: 'ddr5_udimm_16gb', label: 'DDR5 UDIMM 16GB' },
  ];

  const all = [...(priceData.granules || []), ...(priceData.modules || []), ...(priceData.contract || [])];

  container.innerHTML = highlights.map(h => {
    const item = all.find(x => x.id === h.id);
    if (!item) return '';
    return `
      <div class="kpi-card">
        <div class="kpi-label">${h.label}</div>
        <div class="kpi-price">${fmtPrice(item.price_usd)}</div>
        <div class="kpi-change ${pctClass(item.change_dod_pct)}">日环比 ${fmtPct(item.change_dod_pct)}</div>
      </div>
    `;
  }).join('');
}

// === Briefing Summary Card ===
export function renderBriefingSummary(container, briefing) {
  if (!briefing) {
    container.innerHTML = '<h3>今日早报</h3><p>暂无数据</p>';
    return;
  }
  container.innerHTML = `
    <h3>${briefing.title}</h3>
    <p>${briefing.summary}</p>
    <p style="margin-top:8px"><a href="#briefing" style="color:var(--primary)">查看完整早报 →</a></p>
  `;
}

// === Price Table ===
export function renderPriceTable(tbody, items) {
  tbody.innerHTML = items.map(item => {
    const spec = item.spec || item.capacity || item.density || '—';
    return `
      <tr>
        <td><strong>${item.category}</strong> ${item.density || item.form || ''}</td>
        <td>${spec}</td>
        <td><strong>${fmtPrice(item.price_usd)}</strong></td>
        <td class="${pctClass(item.change_dod_pct)}">${fmtPct(item.change_dod_pct)}</td>
        <td class="${pctClass(item.change_wow_pct)}">${fmtPct(item.change_wow_pct)}</td>
        <td>${confidenceBadge(item.confidence || 'low')}</td>
        <td>${item.note || '—'}</td>
      </tr>
    `;
  }).join('');
}

// === Briefing Date List ===
export function renderBriefingList(container, briefingsIndex, onDateClick) {
  container.innerHTML = briefingsIndex.map((b, i) => `
    <div class="date-list-item ${i === 0 ? 'active' : ''}" data-date="${b.date}">
      <div class="date">${b.date}</div>
      <div class="date-summary">${b.summary || ''}</div>
    </div>
  `).join('');

  container.querySelectorAll('.date-list-item').forEach(el => {
    el.addEventListener('click', () => {
      container.querySelectorAll('.date-list-item').forEach(e => e.classList.remove('active'));
      el.classList.add('active');
      onDateClick(el.dataset.date);
    });
  });
}

// === Briefing Content ===
export function renderBriefingContent(container, briefing) {
  if (!briefing) {
    container.innerHTML = '<p class="empty-hint">暂无早报数据</p>';
    return;
  }

  const bodyHtml = typeof marked !== 'undefined'
    ? DOMPurify.sanitize(marked.parse(briefing.body_markdown || ''))
    : '<pre>' + (briefing.body_markdown || '') + '</pre>';

  const outlookHtml = briefing.outlook_markdown
    ? `<div style="margin-top:16px;padding:12px;background:#f0f4ff;border-radius:6px">
        <strong>展望：</strong>${typeof marked !== 'undefined' ? DOMPurify.sanitize(marked.parse(briefing.outlook_markdown)) : briefing.outlook_markdown}
      </div>`
    : '';

  container.innerHTML = `
    <h3>${briefing.title}</h3>
    <div class="briefing-meta">
      ${confidenceBadge(briefing.confidence || 'medium')}
      <span>生成时间：${(briefing.generated_at || '').slice(0, 16).replace('T', ' ')}</span>
    </div>
    <div class="briefing-body">
      ${bodyHtml}
      ${outlookHtml}
    </div>
  `;
}

// === Supply & Demand ===
export function renderSupplyDemand(container, briefing) {
  if (!briefing || !briefing.supply_demand_points?.length) {
    container.innerHTML = '<h3>供需分析要点</h3><p class="empty-hint">数据积累中</p>';
    return;
  }

  const bullish = (briefing.bullish_points || []).map(p => `<li style="color:var(--green)">▲ ${p}</li>`).join('');
  const bearish = (briefing.bearish_points || []).map(p => `<li style="color:var(--red)">▼ ${p}</li>`).join('');

  container.innerHTML = `
    <h3>供需分析要点</h3>
    <ul>
      ${briefing.supply_demand_points.map(p => `<li>${p}</li>`).join('')}
    </ul>
    ${bullish ? `<h4 style="margin-top:12px;font-size:0.9rem">利多</h4><ul>${bullish}</ul>` : ''}
    ${bearish ? `<h4 style="margin-top:8px;font-size:0.9rem">利空</h4><ul>${bearish}</ul>` : ''}
  `;
}

// === News List ===
export function renderNewsList(container, items) {
  if (!items?.length) {
    container.innerHTML = '<p class="empty-hint">暂无行业动态</p>';
    return;
  }

  container.innerHTML = items.map(item => `
    <div class="news-card importance-${item.importance || 'low'}">
      <div class="news-card-header">
        <div class="news-title">
          ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}
        </div>
        <div class="news-meta">
          <span class="vendor-badge">${item.vendor}</span>
          <span>${item.published_date || ''}</span>
        </div>
      </div>
      <div class="news-summary">${item.summary || ''}</div>
      <div class="news-tags">
        ${(item.tags || []).map(t => `<span class="news-tag">${t}</span>`).join('')}
      </div>
    </div>
  `).join('');
}
