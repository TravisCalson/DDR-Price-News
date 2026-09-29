// data.js — JSON loaders with module-level cache

let _latest = null;
let _history = null;
const _briefingCache = {};

export async function loadLatest() {
  if (_latest) return _latest;
  const res = await fetch('data/latest.json');
  if (!res.ok) throw new Error('Failed to load latest.json');
  _latest = await res.json();
  return _latest;
}

export async function loadHistory() {
  if (_history) return _history;
  const res = await fetch('data/history.json');
  if (!res.ok) throw new Error('Failed to load history.json');
  _history = await res.json();
  return _history;
}

export async function loadBriefing(date) {
  if (_briefingCache[date]) return _briefingCache[date];
  const res = await fetch(`data/briefings/${date}.json`);
  if (!res.ok) return null;
  _briefingCache[date] = await res.json();
  return _briefingCache[date];
}
