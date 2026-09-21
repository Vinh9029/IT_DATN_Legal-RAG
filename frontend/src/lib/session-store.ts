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
}

const STORAGE_KEY = 'luuhanh_chat_threads_session';

export function getThreads(): ChatThread[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
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
    messages: []
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
