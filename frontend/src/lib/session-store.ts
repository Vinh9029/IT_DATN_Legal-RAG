export interface LegalChunk {
  chunk_id: string;
  doc_id: string;
  dieu?: string;
  content: string;
  score: number;
  metadata?: {
    so_hieu?: string;
    loai_van_ban?: string;
    co_quan_ban_hanh?: string;
    tinh_trang?: string;
    ngay_ban_hanh?: string;
    ngay_hieu_luc?: string;
    linh_vuc?: string;
    [key: string]: any;
  };
}

export interface VerboseRAGInfo {
  evolvedQuery?: string;
  topKDocs?: LegalChunk[];
  timeTaken?: number;
  stageTimings?: {
    queryEvolution?: number;
    retrieval?: number;
    rerank?: number;
  };
}

export interface SubThreadItem {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

export interface MessageBranch {
  id: string;
  parentMessageId: string;
  title: string;
  parentSnippet: string;
  messages: SubThreadItem[];
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  verboseInfo?: VerboseRAGInfo;
  branch?: MessageBranch;
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
  // Tái dùng chat rỗng sẵn có thay vì tạo thêm, đồng thời dọn các chat rỗng thừa
  const all = getThreads();
  const empty = all.find((t) => t.messages.length === 0);
  if (empty && !firstMessageTitle) {
    const threads = [empty, ...all.filter((t) => t.messages.length > 0)];
    saveThreads(threads);
    return empty;
  }

  const threads = all.filter((t) => t.messages.length > 0);
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

export function deleteMessageFromThread(threadId: string, messageId: string): ChatThread | undefined {
  const threads = getThreads();
  const index = threads.findIndex((t) => t.id === threadId);
  if (index === -1) return undefined;

  threads[index].messages = threads[index].messages.filter((m) => m.id !== messageId);
  saveThreads(threads);
  return threads[index];
}

export function createOrGetBranch(
  threadId: string, 
  messageId: string, 
  parentContent: string
): MessageBranch | undefined {
  const threads = getThreads();
  const threadIndex = threads.findIndex((t) => t.id === threadId);
  if (threadIndex === -1) return undefined;

  const msgIndex = threads[threadIndex].messages.findIndex((m) => m.id === messageId);
  if (msgIndex === -1) return undefined;

  const msg = threads[threadIndex].messages[msgIndex];
  if (msg.branch) {
    return msg.branch;
  }

  // Lấy các dòng đầu tiên của câu trả lời AI làm tiêu đề và snippet
  const lines = parentContent.split('\n').filter(l => l.trim().length > 0);
  const rawTitle = lines[0]?.replace(/[#*`>-]/g, '').trim() || 'Nhánh thảo luận pháp lý';
  const title = rawTitle.length > 40 ? rawTitle.substring(0, 40) + '...' : rawTitle;
  const parentSnippet = parentContent.length > 180 ? parentContent.substring(0, 180) + '...' : parentContent;

  const newBranch: MessageBranch = {
    id: 'branch-' + Date.now(),
    parentMessageId: messageId,
    title,
    parentSnippet,
    messages: [],
    createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
  };

  msg.branch = newBranch;
  threads[threadIndex].messages[msgIndex] = msg;
  saveThreads(threads);
  return newBranch;
}

export function addMessageToBranch(
  threadId: string,
  messageId: string,
  subItem: SubThreadItem
): MessageBranch | undefined {
  const threads = getThreads();
  const threadIndex = threads.findIndex((t) => t.id === threadId);
  if (threadIndex === -1) return undefined;

  const msgIndex = threads[threadIndex].messages.findIndex((m) => m.id === messageId);
  if (msgIndex === -1) return undefined;

  const msg = threads[threadIndex].messages[msgIndex];
  if (!msg.branch) {
    createOrGetBranch(threadId, messageId, msg.content);
  }

  if (msg.branch) {
    msg.branch.messages.push(subItem);
    threads[threadIndex].messages[msgIndex] = msg;
    saveThreads(threads);
    return msg.branch;
  }
  return undefined;
}

export function updateBranchMessages(
  threadId: string,
  messageId: string,
  messages: SubThreadItem[]
): MessageBranch | undefined {
  const threads = getThreads();
  const threadIndex = threads.findIndex((t) => t.id === threadId);
  if (threadIndex === -1) return undefined;

  const msgIndex = threads[threadIndex].messages.findIndex((m) => m.id === messageId);
  if (msgIndex === -1) return undefined;

  const msg = threads[threadIndex].messages[msgIndex];
  if (msg.branch) {
    msg.branch.messages = messages;
    threads[threadIndex].messages[msgIndex] = msg;
    saveThreads(threads);
    return msg.branch;
  }
  return undefined;
}

