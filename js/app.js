// app.js — boot, nav, section switching

import { loadLatest, loadHistory, loadBriefing } from './data.js';
import {
  renderKPIs, renderBriefingSummary, renderPriceTable,
  renderBriefingList, renderBriefingContent,
  renderSupplyDemand, renderNewsList
} from './render.js';
import { renderLineChart } from './charts.js';

let _latest = null;
let _history = null;
let _currentChartDays = 30;

// === Navigation ===
function initNav() {
  const links = document.querySelectorAll('.nav-link');
  links.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const sectionId = link.dataset.section;
      links.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      document.getElementById(sectionId)?.classList.add('active');

      // Render charts when trends section is opened
      if (sectionId === 'trends') {
        renderCharts();
      }
    });
  });
}

// === Price Tab Switching ===
function initPriceTabs() {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      renderPrices(tab.dataset.tab);
    });
  });
}

function renderPrices(tab) {
  const tbody = document.getElementById('price-tbody');
  if (!_latest?.price) return;

  const dataMap = {
    granules: _latest.price.granules || [],
    modules: _latest.price.modules || [],
    contract: _latest.price.contract || [],
  };
  renderPriceTable(tbody, dataMap[tab] || []);
}

// === News Filter ===
function initNewsFilters() {
  const chips = document.querySelectorAll('.chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      renderNews(chip.dataset.vendor);
    });
  });
}

function renderNews(vendor) {
  const container = document.getElementById('news-list');
  const items = _latest?.news?.items || [];
  const filtered = vendor === 'all' ? items : items.filter(n => n.vendor === vendor);
  renderNewsList(container, filtered);
}

// === Charts ===
function initChartRangeButtons() {
  const btns = document.querySelectorAll('.range-btn');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      btns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _currentChartDays = parseInt(btn.dataset.days);
      renderCharts();
    });
  });
}

function renderCharts() {
  if (!_history) return;

  const { series, series_meta } = _history;

  // Check if we have enough data
  const anySeries = Object.values(series || {});
  const totalPoints = anySeries.reduce((acc, pts) => acc + (pts?.length || 0), 0);
  if (totalPoints < 2) {
    document.querySelectorAll('.chart-card').forEach(card => {
      card.innerHTML = '<p class="empty-hint">数据积累中…</p>';
    });
    return;
  }

  const granuleIds = ['ddr4_8gbit', 'ddr4_16gbit', 'ddr5_8gbit', 'ddr5_16gbit'];
  const moduleIds = ['ddr4_udimm_16gb', 'ddr5_udimm_16gb', 'ddr5_rdimm_32gb', 'ddr5_rdimm_64gb'];

  // Filter to only IDs that exist in the data
  const existingGranules = granuleIds.filter(id => series[id]?.length > 0);
  const existingModules = moduleIds.filter(id => series[id]?.length > 0);

  renderLineChart('granule-chart', series, series_meta, existingGranules, _currentChartDays);
  renderLineChart('module-chart', series, series_meta, existingModules, _currentChartDays);
}

// === Briefing Section ===
async function onBriefingDateClick(date) {
  const container = document.getElementById('briefing-content');
  container.innerHTML = '<p class="empty-hint">加载中…</p>';
  const briefing = await loadBriefing(date);
  renderBriefingContent(container, briefing);
}

// === Boot ===
async function boot() {
  try {
    [_latest, _history] = await Promise.all([loadLatest(), loadHistory()]);

    // Update time
    const updateTime = document.getElementById('update-time');
    if (updateTime && _latest?.date) {
      updateTime.textContent = `更新: ${_latest.date}`;
    }

    // Overview
    renderKPIs(document.getElementById('kpi-grid'), _latest.price);
    renderBriefingSummary(document.getElementById('briefing-summary-card'), _latest.briefing);

    // Prices
    renderPrices('granules');

    // Briefing
    const briefingsIndex = _history.briefings_index || [];
    renderBriefingList(document.getElementById('briefing-date-list'), briefingsIndex, onBriefingDateClick);
    // Load latest briefing by default
    if (briefingsIndex.length > 0) {
      onBriefingDateClick(briefingsIndex[0].date);
    }

    // Supply demand
    renderSupplyDemand(document.getElementById('supply-demand'), _latest.briefing);

    // News
    renderNews('all');

    // Init interactions
    initNav();
    initPriceTabs();
    initNewsFilters();
    initChartRangeButtons();

  } catch (err) {
    console.error('Boot failed:', err);
    document.querySelector('.main').innerHTML = `
      <div style="text-align:center;padding:60px 20px">
        <h2>数据加载失败</h2>
        <p style="color:#6b7280;margin-top:8px">${err.message}</p>
      </div>
    `;
  }
}

boot();
