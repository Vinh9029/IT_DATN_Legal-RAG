import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BrandMark } from '@/components/brand-mark';
import { Button } from '@/components/ui/button';
import { LegalDisclaimer } from '@/components/legal-disclaimer';
import { StatusBadge } from '@/components/status-badge';
import { 
  SUGGESTED_QUESTIONS, 
  streamLegalAnswer 
} from '@/lib/chat-service';
import { 
  getThreads, 
  getThread, 
  createThread, 
  addMessageToThread, 
  updateThreadMessages
} from '@/lib/session-store';
import type { ChatMessage, ChatThread } from '@/lib/session-store';
import { 
  Plus, 
  Send, 
  Square, 
  MessageSquare, 
  Bot, 
  User, 
  ArrowLeft, 
  Sparkles,
  RotateCcw
} from 'lucide-react';

export const AssistantPage: React.FC = () => {
  const { threadId } = useParams<{ threadId?: string }>();
  const navigate = useNavigate();

  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [currentThread, setCurrentThread] = useState<ChatThread | null>(null);
  const [inputQuery, setInputQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll down when message updates
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentThread?.messages, isGenerating]);

  // Load threads on mount & handle route threadId
  useEffect(() => {
    const loadedThreads = getThreads();
    setThreads(loadedThreads);

    if (threadId) {
      const existing = getThread(threadId);
      if (existing) {
        setCurrentThread(existing);
      } else {
        // If URL threadId doesn't exist in session, create it fresh
        const newT: ChatThread = {
          id: threadId,
          title: 'Cuộc trò chuyện mới',
          createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
          messages: []
        };
        const all = [newT, ...loadedThreads];
        setThreads(all);
        setCurrentThread(newT);
      }
    } else {
      // If /tro-ly without threadId, create a new thread and navigate
      const newT = createThread();
      navigate(`/tro-ly/${newT.id}`, { replace: true });
    }
  }, [threadId]);

  const handleNewThread = () => {
    const newT = createThread();
    setThreads(getThreads());
    setCurrentThread(newT);
    navigate(`/tro-ly/${newT.id}`);
    setSidebarOpen(false);
  };

  const handleSelectThread = (id: string) => {
    navigate(`/tro-ly/${id}`);
    setSidebarOpen(false);
  };

  const handleSendPrompt = async (textToSend?: string) => {
    const query = (textToSend || inputQuery).trim();
    if (!query || isGenerating || !currentThread) return;

    setInputQuery('');
    const userMsg: ChatMessage = {
      id: 'msg-user-' + Date.now(),
      sender: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
    };

    // Add user message to current thread
    const updatedThread = addMessageToThread(currentThread.id, userMsg);
    if (updatedThread) {
      setCurrentThread({ ...updatedThread });
      setThreads(getThreads());
    }

    // Prepare assistant response message holder
    const assistantMsgId = 'msg-ai-' + Date.now();
    const initialAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      isStreaming: true
    };

    let currentMessages = [...(updatedThread?.messages || currentThread.messages), initialAssistantMsg];
    setCurrentThread(prev => prev ? { ...prev, messages: currentMessages } : null);
    setIsGenerating(true);

    abortControllerRef.current = new AbortController();

    await streamLegalAnswer(
      query,
      {
        onChunk: (chunkText) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, content: chunkText, isStreaming: true } : m
          );
          setCurrentThread(prev => prev ? { ...prev, messages: [...currentMessages] } : null);
        },
        onComplete: (fullText) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, content: fullText, isStreaming: false } : m
          );
          if (currentThread) {
            updateThreadMessages(currentThread.id, currentMessages);
            setCurrentThread(prev => prev ? { ...prev, messages: currentMessages } : null);
            setThreads(getThreads());
          }
          setIsGenerating(false);
        },
        onError: (err) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, content: `⚠️ **Lỗi**: ${err.message}`, isStreaming: false } : m
          );
          if (currentThread) {
            updateThreadMessages(currentThread.id, currentMessages);
            setCurrentThread(prev => prev ? { ...prev, messages: currentMessages } : null);
          }
          setIsGenerating(false);
        }
      },
      abortControllerRef.current.signal
    );
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsGenerating(false);
    }
  };

  // Helper custom renderer for Markdown content including StatusBadges
  const renderMarkdownContent = (content: string) => {
    // Custom replacement for status badge tags like [Còn hiệu lực]
    return (
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-4 leading-relaxed text-[#0F172A]">{children}</p>,
          h1: ({ children }) => <h1 className="text-2xl font-bold text-[#0F172A] mt-6 mb-3 border-b pb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-xl font-bold text-[#0F172A] mt-5 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-lg font-bold text-[#1E3A8A] mt-4 mb-2">{children}</h3>,
          h4: ({ children }) => <h4 className="text-base font-semibold text-[#0F172A] mt-3 mb-1">{children}</h4>,
          ul: ({ children }) => <ul className="list-disc list-inside space-y-2 mb-4 text-[#0F172A]">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside space-y-2 mb-4 text-[#0F172A]">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => (
            <div className="my-4 border-l-4 border-[#2563EB] bg-[#2563EB]/5 p-4 rounded-r-md italic text-slate-700">
              {children}
            </div>
          ),
          strong: ({ children }) => {
            const text = String(children);
            if (text.includes('Status Badge:') || text.includes('Còn hiệu lực') || text.includes('Hết hiệu lực') || text.includes('Sửa đổi')) {
              return <StatusBadge status={text} />;
            }
            return <strong className="font-semibold text-[#0F172A]">{children}</strong>;
          },
          code: ({ children }) => (
            <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-[#2563EB] font-medium border border-slate-200">
              {children}
            </code>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    );
  };

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-[#0F172A] overflow-hidden">
      {/* SIDEBAR - Desktop & Mobile Drawer */}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-300 md:static md:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        {/* Sidebar Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4">
          <BrandMark />
          <button 
            onClick={() => setSidebarOpen(false)} 
            className="md:hidden text-slate-400 hover:text-slate-600 p-1"
          >
            ✕
          </button>
        </div>

        {/* Action Button: New Thread */}
        <div className="p-4 border-b border-slate-100">
          <Button
            variant="accent"
            size="md"
            onClick={handleNewThread}
            className="w-full justify-center gap-2 font-mono text-xs uppercase tracking-wider"
          >
            <Plus className="size-4" />
            <span>Cuộc trò chuyện mới</span>
          </Button>
        </div>

        {/* Thread History List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-400">
            Phiên hiện tại ({threads.length})
          </div>

          {threads.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-400 font-mono">
              Chưa có cuộc trò chuyện nào trong phiên.
            </div>
          ) : (
            threads.map((t) => {
              const isActive = t.id === threadId;
              return (
                <button
                  key={t.id}
                  onClick={() => handleSelectThread(t.id)}
                  className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs transition-colors ${
                    isActive 
                      ? 'bg-[#1E3A8A] text-white font-medium shadow-xs' 
                      : 'text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  <MessageSquare className={`size-4 shrink-0 ${isActive ? 'text-[#2563EB]' : 'text-slate-400'}`} />
                  <div className="flex-1 overflow-hidden">
                    <p className="truncate">{t.title}</p>
                    <span className={`font-mono text-[9px] ${isActive ? 'text-slate-300' : 'text-slate-400'}`}>
                      {t.createdAt}
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="border-t border-slate-200 p-4 bg-slate-50">
          <Link to="/" className="flex items-center gap-2 text-xs font-mono text-slate-600 hover:text-[#2563EB]">
            <ArrowLeft className="size-4" />
            <span>Quay lại Trang chủ</span>
          </Link>
        </div>
      </aside>

      {/* MAIN CHAT AREA */}
      <div className="flex flex-1 flex-col h-full overflow-hidden">
        {/* Top Chat Bar */}
        <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 md:px-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden rounded-md border border-slate-200 p-2 text-slate-600 hover:bg-slate-100"
            >
              <MessageSquare className="size-5" />
            </button>
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-lg bg-[#0F172A] text-white font-bold text-sm">
                L
              </div>
              <div>
                <h2 className="font-semibold text-sm text-[#0F172A]">Trợ lý Pháp lý AI</h2>
                <p className="font-mono text-[10px] text-[#2563EB]">Online · RAG Vietnamese Law Engine</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleNewThread}
              className="hidden sm:inline-flex"
            >
              <RotateCcw className="size-3.5" />
              <span>Xóa sạch & Tạo mới</span>
            </Button>
          </div>
        </header>

        {/* Legal Warning Header Banner */}
        <LegalDisclaimer compact />

        {/* MESSAGES / CHAT CONTAINER */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
          {/* EMPTY STATE: SUGGESTED QUESTIONS (4 CÂU HỎI GỢI Ý) */}
          {(!currentThread || currentThread.messages.length === 0) && (
            <div className="mx-auto max-w-3xl pt-6 pb-12">
              <div className="text-center">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[#2563EB]/10 text-[#2563EB]">
                  <Sparkles className="size-7" />
                </div>
                <h2 className="mt-4 font-display text-3xl uppercase tracking-tight text-[#0F172A]">
                  Trợ lý Pháp luật Việt Nam
                </h2>
                <p className="mt-2 text-sm text-slate-600 max-w-md mx-auto">
                  Đặt câu hỏi bằng tiếng Việt để tra cứu căn cứ pháp lý, hiệu lực văn bản và phương án giải quyết vụ việc.
                </p>
              </div>

              {/* 4 SUGGESTED QUESTIONS CARDS */}
              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendPrompt(q.prompt)}
                    className="group flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 text-left transition-all hover:border-[#2563EB] hover:shadow-md"
                  >
                    <div>
                      <span className="inline-block rounded-md bg-slate-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#2563EB] group-hover:bg-[#2563EB]/10">
                        {q.category}
                      </span>
                      <h4 className="mt-2 font-bold text-sm text-[#0F172A] group-hover:text-[#2563EB]">
                        {q.title}
                      </h4>
                      <p className="mt-1 text-xs text-slate-500 line-clamp-2 leading-relaxed">
                        "{q.prompt}"
                      </p>
                    </div>
                    <div className="mt-4 flex items-center gap-1 font-mono text-[11px] font-medium text-[#2563EB]">
                      <span>Hỏi ngay câu này</span>
                      <ArrowLeft className="size-3 rotate-180 transition-transform group-hover:translate-x-1" />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* CHAT MESSAGES LIST */}
          {currentThread?.messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-4 max-w-4xl mx-auto ${
                msg.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.sender === 'assistant' && (
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[#0F172A] text-white font-bold text-sm shadow-xs">
                  <Bot className="size-5 text-[#2563EB]" />
                </div>
              )}

              <div className={`flex flex-col max-w-[85%] ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono text-[10px] text-slate-400">
                    {msg.sender === 'user' ? 'Bạn' : 'Trợ lý LƯU HÀNH'} · {msg.timestamp}
                  </span>
                </div>

                <div
                  className={`rounded-2xl px-5 py-4 text-sm leading-relaxed shadow-xs ${
                    msg.sender === 'user'
                      ? 'bg-[#0F172A] text-white font-medium rounded-tr-none'
                      : 'bg-white border border-slate-200 text-[#0F172A] rounded-tl-none'
                  }`}
                >
                  {msg.sender === 'user' ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <div className={msg.isStreaming ? 'typing-cursor' : ''}>
                      {msg.content ? (
                        renderMarkdownContent(msg.content)
                      ) : (
                        /* DYNAMIC TYPING INDICATOR / THINKING STATUS */
                        <div className="flex items-center gap-3 py-2 text-slate-500 font-mono text-xs">
                          <div className="flex space-x-1">
                            <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '0ms' }} />
                            <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '150ms' }} />
                            <div className="size-2 rounded-full bg-[#2563EB] animate-bounce" style={{ animationDelay: '300ms' }} />
                          </div>
                          <span>Đang tra cứu căn cứ pháp lý & suy nghĩ...</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {msg.sender === 'user' && (
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-700 font-bold text-sm">
                  <User className="size-5" />
                </div>
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* INPUT FORM CONTAINER */}
        <div className="border-t border-slate-200 bg-white p-4 md:px-6">
          <div className="mx-auto max-w-4xl">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendPrompt();
              }}
              className="relative flex items-center rounded-xl border-2 border-slate-300 bg-white p-2 transition-within focus-within:border-[#2563EB] focus-within:ring-2 focus-within:ring-[#2563EB]/20 shadow-xs"
            >
              <textarea
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendPrompt();
                  }
                }}
                placeholder="Nhập tình huống hoặc câu hỏi pháp lý của bạn... (Ấn Enter để gửi)"
                rows={1}
                className="flex-1 resize-none bg-transparent px-3 py-2 text-sm text-[#0F172A] placeholder-slate-400 focus:outline-none max-h-32"
              />

              <div className="flex items-center gap-2">
                {isGenerating ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleStopGeneration}
                    className="text-red-600 border-red-200 hover:bg-red-50 font-mono text-xs"
                  >
                    <Square className="size-3.5 fill-red-600" />
                    <span>Dừng</span>
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    variant="accent"
                    size="sm"
                    disabled={!inputQuery.trim()}
                    className="gap-1.5 font-mono text-xs uppercase"
                  >
                    <span>Gửi</span>
                    <Send className="size-3.5" />
                  </Button>
                )}
              </div>
            </form>
            <p className="mt-2 text-center font-mono text-[10px] text-slate-400">
              LƯU HÀNH AI Trợ lý Pháp lý · Dữ liệu phản hồi được xử lý trong phiên làm việc hiện tại
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
