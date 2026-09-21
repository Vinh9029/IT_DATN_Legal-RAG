export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

export interface ChatThread {
  id: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
  isPinned?: boolean;
  themeBg?: 'default' | 'dark' | 'ivory' | 'grid';
}

const STORAGE_KEY = 'luuhanh_chat_threads_session';

export function getThreads(): ChatThread[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const threads: ChatThread[] = JSON.parse(raw);
    // Sort pinned threads to top
    return threads.sort((a, b) => (b.isPinned ? 1 : 0) - (a.isPinned ? 1 : 0));
  } catch (e) {
    console.error('Lỗi khi đọc session threads:', e);
    return [];
  }
}

export function saveThreads(threads: ChatThread[]): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
  } catch (e) {
    console.error('Lỗi khi lưu session threads:', e);
  }
}

export function createThread(firstMessageTitle?: string): ChatThread {
  const threads = getThreads();
  const newThread: ChatThread = {
    id: 'thread-' + Date.now() + '-' + Math.random().toString(36).substring(2, 7),
    title: firstMessageTitle ? (firstMessageTitle.length > 30 ? firstMessageTitle.substring(0, 30) + '...' : firstMessageTitle) : 'Cuộc trò chuyện mới',
    createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
    messages: [],
    isPinned: false,
    themeBg: 'default'
  };
  threads.unshift(newThread);
  saveThreads(threads);
  return newThread;
}

export function getThread(id: string): ChatThread | undefined {
  const threads = getThreads();
  return threads.find((t) => t.id === id);
}

export function addMessageToThread(threadId: string, message: ChatMessage): ChatThread | undefined {
  const threads = getThreads();
  const threadIndex = threads.findIndex((t) => t.id === threadId);
  if (threadIndex === -1) return undefined;

  const thread = threads[threadIndex];
  thread.messages.push(message);

  // Update thread title if first message from user
  if (message.sender === 'user' && thread.messages.filter(m => m.sender === 'user').length === 1) {
    thread.title = message.content.length > 32 ? message.content.substring(0, 32) + '...' : message.content;
  }

  threads[threadIndex] = thread;
  saveThreads(threads);
  return thread;
}

export function updateThreadMessages(threadId: string, messages: ChatMessage[]): void {
  const threads = getThreads();
  const threadIndex = threads.findIndex((t) => t.id === threadId);
  if (threadIndex === -1) return;

  threads[threadIndex].messages = messages;
  saveThreads(threads);
}

export function renameThread(threadId: string, newTitle: string): ChatThread | undefined {
  const threads = getThreads();
  const index = threads.findIndex((t) => t.id === threadId);
  if (index === -1) return undefined;

  threads[index].title = newTitle;
  saveThreads(threads);
  return threads[index];
}

export function togglePinThread(threadId: string): ChatThread | undefined {
  const threads = getThreads();
  const index = threads.findIndex((t) => t.id === threadId);
  if (index === -1) return undefined;

  threads[index].isPinned = !threads[index].isPinned;
  saveThreads(threads);
  return threads[index];
}

export function updateThreadTheme(threadId: string, themeBg: 'default' | 'dark' | 'ivory' | 'grid'): ChatThread | undefined {
  const threads = getThreads();
  const index = threads.findIndex((t) => t.id === threadId);
  if (index === -1) return undefined;

  threads[index].themeBg = themeBg;
  saveThreads(threads);
  return threads[index];
}

export function deleteThread(threadId: string): void {
  let threads = getThreads();
  threads = threads.filter((t) => t.id !== threadId);
  saveThreads(threads);
}
