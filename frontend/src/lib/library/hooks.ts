import { useCallback, useEffect, useState } from 'react';
import { libraryService } from './library-service';
import type { LawDocument, LawSummary } from './types';

export type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; error: Error };

/** Tải một tài nguyên theo `key`; đổi key thì tải lại, `retry()` để thử lại sau lỗi */
function useLoad<T>(key: string | null, load: () => Promise<T>): [LoadState<T>, () => void] {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState<T> & { key?: string | null }>({ status: 'loading' });

  useEffect(() => {
    if (key === null) return;
    let alive = true;
    load().then(
      (data) => alive && setState({ status: 'ready', data, key }),
      (error: unknown) => alive && setState({ status: 'error', error: error instanceof Error ? error : new Error(String(error)), key }),
    );
    return () => {
      alive = false;
    };
    // `load` đổi theo key — key là đủ
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);

  const retry = useCallback(() => {
    setState({ status: 'loading' });
    setAttempt((n) => n + 1);
  }, []);

  // Đang chuyển sang key mới mà kết quả cũ còn đó → coi như đang tải, tránh chớp nội dung cũ
  return [state.key === key ? state : { status: 'loading' }, retry];
}

export function useLibraryIndex() {
  return useLoad<LawSummary[]>('index', () => libraryService.getIndex());
}

export function useLaw(lawId: string | undefined) {
  return useLoad<LawDocument>(lawId ?? null, () => libraryService.getLaw(lawId!));
}
