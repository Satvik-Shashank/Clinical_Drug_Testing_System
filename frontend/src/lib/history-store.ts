import type { HistoryEntry, SafetyCheckRequest, SafetyCheckResponse } from "./safety-types";

const KEY = "cdse:history:v1";
const MAX = 25;

function isBrowser() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function loadHistory(): HistoryEntry[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveHistoryEntry(
  request: SafetyCheckRequest,
  response: SafetyCheckResponse,
): HistoryEntry {
  const entry: HistoryEntry = {
    id: `chk_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    timestamp: Date.now(),
    request,
    response,
  };
  if (!isBrowser()) return entry;
  try {
    const next = [entry, ...loadHistory()].slice(0, MAX);
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* quota exceeded — ignore */
  }
  return entry;
}

export function clearHistory() {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
