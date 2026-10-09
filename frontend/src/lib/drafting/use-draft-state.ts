import { useCallback, useReducer } from 'react';
import type { FieldEdit, FieldValue, FieldValues } from './types';
import { sameValue } from './values';

// Giá trị các ô + lịch sử hoàn tác. Mọi thay đổi (người gõ, AI sửa, hoàn tác đề xuất AI) đều đi qua
// đây thành một "bước" trong lịch sử, nên Ctrl+Z quay lui được cả thay đổi của AI.

export type EditSource = 'user' | 'ai';

interface Step {
  changes: FieldEdit[];
  source: EditSource;
  /** Gõ liên tục vào cùng một ô thì gộp thành một bước */
  coalesceKey?: string;
  at: number;
}

interface State {
  values: FieldValues;
  past: Step[];
  future: Step[];
  /** Ô vừa bị đổi bởi AI/hoàn tác — để trang giấy nháy sáng chỗ đó; nonce đổi mỗi lần */
  flash: { fields: string[]; nonce: number };
}

type Action =
  | { type: 'reset'; values: FieldValues }
  | { type: 'set'; field: string; value: FieldValue; coalesce: boolean }
  | { type: 'apply'; changes: FieldEdit[]; source: EditSource }
  | { type: 'undo' }
  | { type: 'redo' };

const HISTORY_LIMIT = 200;
const COALESCE_MS = 1500;

const applyChanges = (values: FieldValues, changes: FieldEdit[], dir: 'after' | 'before'): FieldValues => {
  const next = { ...values };
  for (const c of changes) next[c.field] = c[dir];
  return next;
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'reset':
      return { values: action.values, past: [], future: [], flash: { fields: [], nonce: 0 } };

    case 'set': {
      const before = state.values[action.field];
      if (sameValue(before, action.value)) return state;
      const now = Date.now();
      const key = `user:${action.field}`;
      const top = state.past[state.past.length - 1];
      const values = { ...state.values, [action.field]: action.value };
      if (action.coalesce && top?.coalesceKey === key && now - top.at < COALESCE_MS) {
        const merged: Step = { ...top, changes: [{ ...top.changes[0], after: action.value }], at: now };
        return { ...state, values, past: [...state.past.slice(0, -1), merged], future: [] };
      }
      const step: Step = { changes: [{ field: action.field, before, after: action.value }], source: 'user', coalesceKey: action.coalesce ? key : undefined, at: now };
      return { ...state, values, past: [...state.past, step].slice(-HISTORY_LIMIT), future: [] };
    }

    case 'apply': {
      const changes = action.changes.filter((c) => !sameValue(state.values[c.field], c.after));
      if (!changes.length) return state;
      const step: Step = { changes, source: action.source, at: Date.now() };
      return {
        values: applyChanges(state.values, changes, 'after'),
        past: [...state.past, step].slice(-HISTORY_LIMIT),
        future: [],
        flash: action.source === 'ai' ? { fields: changes.map((c) => c.field), nonce: state.flash.nonce + 1 } : state.flash,
      };
    }

    case 'undo': {
      const step = state.past[state.past.length - 1];
      if (!step) return state;
      return {
        values: applyChanges(state.values, [...step.changes].reverse(), 'before'),
        past: state.past.slice(0, -1),
        future: [step, ...state.future],
        flash: { fields: step.changes.map((c) => c.field), nonce: state.flash.nonce + 1 },
      };
    }

    case 'redo': {
      const step = state.future[0];
      if (!step) return state;
      return {
        values: applyChanges(state.values, step.changes, 'after'),
        past: [...state.past, step],
        future: state.future.slice(1),
        flash: { fields: step.changes.map((c) => c.field), nonce: state.flash.nonce + 1 },
      };
    }
  }
}

export function useDraftState(initial: FieldValues) {
  const [state, dispatch] = useReducer(reducer, initial, (values) => ({ values, past: [], future: [], flash: { fields: [], nonce: 0 } }));

  const setField = useCallback((field: string, value: FieldValue, coalesce = true) => dispatch({ type: 'set', field, value, coalesce }), []);
  const applyEdits = useCallback((changes: FieldEdit[], source: EditSource = 'ai') => dispatch({ type: 'apply', changes, source }), []);
  const undo = useCallback(() => dispatch({ type: 'undo' }), []);
  const redo = useCallback(() => dispatch({ type: 'redo' }), []);
  const reset = useCallback((values: FieldValues) => dispatch({ type: 'reset', values }), []);

  return {
    values: state.values,
    flash: state.flash,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    setField,
    applyEdits,
    undo,
    redo,
    reset,
  };
}

// ── Trạng thái từng đề xuất của AI (suy ra từ giá trị hiện tại) ─────

export type EditStatus = 'applied' | 'reverted' | 'changed';

export function editStatus(edit: FieldEdit, values: FieldValues): EditStatus {
  if (sameValue(values[edit.field], edit.after)) return 'applied';
  if (sameValue(values[edit.field], edit.before)) return 'reverted';
  return 'changed';
}
