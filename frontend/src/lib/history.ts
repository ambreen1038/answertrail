"use client";

import { useSyncExternalStore } from "react";

/** The list of conversations shown under "Recent chats".
 *
 *  Signed out: the list lives in this browser only (localStorage). The server has no account to attach
 *  a chat to, so a conversation's random id is the only key, and this list is how the browser
 *  remembers which ids are its own. Clearing site data forgets them.
 *
 *  Signed in: the server's list for the account is the truth. It is kept in memory only, never
 *  written to localStorage, so signing out on a shared computer leaves no chats behind. */
export type ChatRef = { id: string; title: string; updatedAt: number };

const KEY = "answertrail.chats";
const EMPTY: ChatRef[] = [];
const listeners = new Set<() => void>();
let cache: ChatRef[] | null = null;
let accountMode = false;

function read(): ChatRef[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((c) => c && typeof c.id === "string") : [];
  } catch {
    return [];
  }
}

function write(next: ChatRef[]) {
  cache = next;
  if (!accountMode) {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* private mode or full: the in-memory list still works for this tab */
    }
  }
  listeners.forEach((l) => l());
}

function getSnapshot(): ChatRef[] {
  if (cache === null) cache = accountMode ? [] : read();
  return cache;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY && !accountMode) {
      cache = null; // another tab changed it
      cb();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function useChats(): ChatRef[] {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY);
}

export function rememberChat(id: string, title: string) {
  const others = getSnapshot().filter((c) => c.id !== id);
  write([{ id, title, updatedAt: Date.now() }, ...others].slice(0, 30));
}

export function touchChat(id: string) {
  const list = getSnapshot();
  const found = list.find((c) => c.id === id);
  if (found) write([{ ...found, updatedAt: Date.now() }, ...list.filter((c) => c.id !== id)]);
}

export function forgetChat(id: string) {
  write(getSnapshot().filter((c) => c.id !== id));
}

// ---- switching between the two modes (called by the account provider)

/** Someone signed in: show the account's chats (filled in by setServerChats) instead of the browser's. */
export function enterAccountMode() {
  if (accountMode) return;
  accountMode = true;
  cache = [];
  listeners.forEach((l) => l());
}

/** Signed out again: back to this browser's own list. */
export function leaveAccountMode() {
  if (!accountMode) return;
  accountMode = false;
  cache = null;
  listeners.forEach((l) => l());
}

export function setServerChats(list: { id: string; title: string; updated_at: string }[]) {
  if (!accountMode) return;
  cache = list.map((c) => ({ id: c.id, title: c.title, updatedAt: Date.parse(c.updated_at) || 0 }));
  listeners.forEach((l) => l());
}

/** The ids stored in the browser (never the signed-in list), so they can be moved into the account. */
export function localChatIds(): string[] {
  return read().map((c) => c.id);
}

export function clearLocalChats() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
