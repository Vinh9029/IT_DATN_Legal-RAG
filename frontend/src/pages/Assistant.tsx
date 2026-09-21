import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Brand_mark } from '@/components/Brand_mark';
import { Button } from '@/components/ui/Button';
import { Legal_disclaimer } from '@/components/Legal_disclaimer';
import { Status_badge } from '@/components/Status_badge';
import { Profile_modal } from '@/components/Profile_modal';
import { useAuth } from '@/lib/auth-context';
import { 
  SUGGESTED_QUESTIONS, 
  streamLegalAnswer 
} from '@/lib/chat-service';
import { 
  getThreads, 
  getThread, 
  createThread, 
  addMessageToThread, 
  updateThreadMessages,
  renameThread,
  togglePinThread,
  updateThreadTheme,
  deleteThread
} from '@/lib/session-store';
import type { ChatMessage, ChatThread } from '@/lib/session-store';
import { 
  Plus, 
  Send, 
  Square, 
  MessageSquare, 
  User as UserIcon, 
  ArrowLeft, 
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Moon,
  Sun,
  Pin,
  Edit2,
  Trash2,
  Palette,
  LogOut
} from 'lucide-react';

export const Assistant: React.FC = () => {
  const { threadId } = useParams<{ threadId?: string }>();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();

  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [currentThread, setCurrentThread] = useState<ChatThread | null>(null);
  const [inputQuery, setInputQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarRenameId, setSidebarRenameId] = useState<string | null>(null);
  const [sidebarRenameValue, setSidebarRenameValue] = useState('');

  // Settings & Theme states
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [isNightMode, setIsNightMode] = useState(false);
  const [activeTheme, setActiveTheme] = useState<'default' | 'dark' | 'ivory' | 'grid'>('default');
  const [isRenaming, setIsRenaming] = useState(false);
  const [newTitleInput, setNewTitleInput] = useState('');

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const creatingThreadRef = useRef(false);

  const userAvatar = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentThread?.messages, isGenerating]);

  useEffect(() => {
    const loadedThreads = getThreads();
    setThreads(loadedThreads);

    if (threadId) {
      creatingThreadRef.current = false;
      const existing = getThread(threadId);
      if (existing) {
        setCurrentThread(existing);
        if (existing.themeBg) setActiveTheme(existing.themeBg);
      } else {
        const newT: ChatThread = {
          id: threadId,
          title: 'Cuộc trò chuyện mới',
          createdAt: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
          messages: [],
          themeBg: 'default'
        };
        const all = [newT, ...loadedThreads];
        setThreads(all);
        setCurrentThread(newT);
      }
    } else {
      // Prevent double creation: only create once per navigation to /tro-ly
      if (!creatingThreadRef.current) {
        creatingThreadRef.current = true;
        const newT = createThread();
        navigate(`/tro-ly/${newT.id}`, { replace: true });
      }
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

  const handleTogglePin = () => {
    if (!currentThread) return;
    const updated = togglePinThread(currentThread.id);
    if (updated) {
      setCurrentThread({ ...updated });
      setThreads(getThreads());
    }
  };

  const handleRenameSubmit = () => {
    if (!currentThread || !newTitleInput.trim()) return;
    const updated = renameThread(currentThread.id, newTitleInput.trim());
    if (updated) {
      setCurrentThread({ ...updated });
      setThreads(getThreads());
    }
    setIsRenaming(false);
  };

  const handleDeleteCurrent = () => {
    if (!currentThread) return;
    deleteThread(currentThread.id);
    const remaining = getThreads();
    setThreads(remaining);
    if (remaining.length > 0) {
      navigate(`/tro-ly/${remaining[0].id}`);
    } else {
      handleNewThread();
    }
    setSettingsOpen(false);
  };

  const handleChangeTheme = (theme: 'default' | 'dark' | 'ivory' | 'grid') => {
    setActiveTheme(theme);
    if (theme === 'dark') setIsNightMode(true);
    else setIsNightMode(false);

    if (currentThread) {
      updateThreadTheme(currentThread.id, theme);
      setThreads(getThreads());
    }
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

    const updatedThread = addMessageToThread(currentThread.id, userMsg);
    if (updatedThread) {
      setCurrentThread({ ...updatedThread });
      setThreads(getThreads());
    }

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

  const renderMarkdownContent = (content: string) => {
    return (
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-4 leading-relaxed">{children}</p>,
          h1: ({ children }) => <h1 className="text-2xl font-bold mt-6 mb-3 border-b pb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-xl font-bold mt-5 mb-2">{children}</h2>,
          h3: ({ children }) => <h3 className="text-lg font-bold text-[#2563EB] mt-4 mb-2">{children}</h3>,
          h4: ({ children }) => <h4 className="text-base font-semibold mt-3 mb-1">{children}</h4>,
          ul: ({ children }) => <ul className="list-disc list-inside space-y-2 mb-4">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal list-inside space-y-2 mb-4">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => (
            <div className="my-4 border-l-4 border-[#2563EB] bg-[#2563EB]/10 p-4 rounded-r-md italic">
              {children}
            </div>
          ),
          strong: ({ children }) => {
            const text = String(children);
            if (text.includes('Status Badge:') || text.includes('Còn hiệu lực') || text.includes('Hết hiệu lực') || text.includes('Sửa đổi')) {
              return <Status_badge status={text} />;
            }
            return <strong className="font-semibold">{children}</strong>;
          },
          code: ({ children }) => (
            <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-[#2563EB] font-medium border border-slate-200">
              {children}
            </code>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    );
  };

  // Determine chat area theme background styles
  const getThemeClass = () => {
    if (isNightMode) return 'bg-[#0F172A] text-white';
    switch (activeTheme) {
      case 'dark':
        return 'bg-[#0F172A] text-white';
      case 'ivory':
        return 'bg-[#FBF9F5] text-[#0F172A]';
      case 'grid':
        return 'bg-[#F8FAFC] text-[#0F172A] bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] [background-size:16px_16px]';
      default:
        return 'bg-[#F8FAFC] text-[#0F172A]';
    }
  };

  const isDark = isNightMode || activeTheme === 'dark';

  return (
    <div className={`flex h-screen overflow-hidden ${isDark ? 'dark' : ''}`}>
      {/* SIDEBAR - LEFT PANEL WITH CLOSE/EXPAND FEATURE */}
      <aside 
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-200 bg-white transition-all duration-300 md:static ${
          sidebarCollapsed ? 'w-0 overflow-hidden border-none opacity-0' : 'w-72 opacity-100'
        } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        {/* Sidebar Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4">
          <Brand_mark />
          <button 
            onClick={() => setSidebarCollapsed(true)} 
            title="Thu gọn Sidebar"
            className="hidden md:flex rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 cursor-pointer"
          >
            <PanelLeftClose className="size-5" />
          </button>
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
          <div className="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span>Phiên hiện tại ({threads.length})</span>
          </div>

          {threads.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-400 font-mono">
              Chưa có cuộc trò chuyện nào trong phiên.
            </div>
          ) : (
            threads.map((t) => {
              const isActive = t.id === threadId;
              const isSidebarRenaming = sidebarRenameId === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => handleSelectThread(t.id)}
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setSidebarRenameId(t.id);
                    setSidebarRenameValue(t.title);
                  }}
                  className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs transition-colors cursor-pointer ${
                    isActive 
                      ? 'bg-[#1E3A8A] text-white font-medium shadow-xs' 
                      : 'text-slate-700 hover:bg-slate-100'
                  }`}
                  title="Nhấp đúp để đổi tên"
                >
                  <MessageSquare className={`size-4 shrink-0 ${isActive ? 'text-[#2563EB]' : 'text-slate-400'}`} />
                  <div className="flex-1 overflow-hidden">
                    <div className="flex items-center justify-between gap-1">
                      {isSidebarRenaming ? (
                        <input
                          type="text"
                          value={sidebarRenameValue}
                          onChange={(e) => setSidebarRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            e.stopPropagation();
                            if (e.key === 'Enter') {
                              if (sidebarRenameValue.trim()) {
                                const updated = renameThread(t.id, sidebarRenameValue.trim());
                                if (updated && currentThread?.id === t.id) {
                                  setCurrentThread({ ...updated });
                                }
                                setThreads(getThreads());
                              }
                              setSidebarRenameId(null);
                            }
                            if (e.key === 'Escape') setSidebarRenameId(null);
                          }}
                          onBlur={() => {
                            if (sidebarRenameValue.trim()) {
                              const updated = renameThread(t.id, sidebarRenameValue.trim());
                              if (updated && currentThread?.id === t.id) {
                                setCurrentThread({ ...updated });
                              }
                              setThreads(getThreads());
                            }
                            setSidebarRenameId(null);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="w-full rounded border border-[#2563EB] bg-white px-1.5 py-0.5 text-xs text-[#0F172A] font-medium focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
                          autoFocus
                        />
                      ) : (
                        <p className="truncate">{t.title}</p>
                      )}
                      {t.isPinned && (
                        <Pin className="size-3 text-amber-400 shrink-0 fill-amber-400" />
                      )}
                    </div>
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
      <div className={`flex flex-1 flex-col h-full overflow-hidden ${getThemeClass()}`}>
        {/* Top Chat Bar */}
        <header className={`flex h-16 items-center justify-between border-b px-4 md:px-6 transition-colors ${
          isDark ? 'border-slate-800 bg-slate-900 text-white' : 'border-slate-200 bg-white text-[#0F172A]'
        }`}>
          <div className="flex items-center gap-3">
            {/* Sidebar Expand Toggle Button */}
            {sidebarCollapsed && (
              <button
                onClick={() => setSidebarCollapsed(false)}
                title="Mở rộng Sidebar"
                className={`hidden md:flex rounded-lg border p-2 cursor-pointer ${
                  isDark ? 'border-slate-800 text-slate-300 hover:bg-slate-800' : 'border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <PanelLeftOpen className="size-5" />
              </button>
            )}
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden rounded-md border border-slate-200 p-2 text-slate-600 hover:bg-slate-100"
            >
              <MessageSquare className="size-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-xl border border-slate-200 bg-white overflow-hidden p-0.5 shadow-xs">
                <img src="/logo.png" alt="Logo" className="size-full object-contain" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  {isRenaming ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        value={newTitleInput}
                        onChange={(e) => setNewTitleInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRenameSubmit();
                          if (e.key === 'Escape') setIsRenaming(false);
                        }}
                        className="rounded border border-[#2563EB] px-2 py-0.5 text-xs text-[#0F172A] font-semibold"
                        autoFocus
                      />
                      <Button size="sm" variant="accent" onClick={handleRenameSubmit} className="h-6 px-2 text-[10px]">
                        Lưu
                      </Button>
                    </div>
                  ) : (
                    <h2 
                      className="font-semibold text-sm truncate max-w-[200px] sm:max-w-xs cursor-pointer hover:text-[#2563EB] transition-colors"
                      onDoubleClick={() => {
                        setNewTitleInput(currentThread?.title || '');
                        setIsRenaming(true);
                      }}
                      title="Nhấp đúp để đổi tên"
                    >
                      {currentThread?.title || 'Trợ lý Pháp lý AI'}
                    </h2>
                  )}
                  {currentThread?.isPinned && (
                    <Pin className="size-3.5 text-amber-500 fill-amber-500 shrink-0" />
                  )}
                </div>
                <p className="font-mono text-[10px] text-[#2563EB]">Online · RAG Vietnamese Law Engine</p>
              </div>
            </div>
          </div>

          {/* Action Toolbar: User Profile Avatar + Rearranged Settings Menu at far right */}
          <div className="flex items-center gap-3">
            {/* User Profile Avatar (Opens Profile Modal) */}
            <button
              onClick={() => setProfileModalOpen(true)}
              title="Quản lý Hồ sơ User Avatar"
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1 pr-3 shadow-xs hover:border-[#2563EB] transition-colors cursor-pointer"
            >
              {userAvatar ? (
                <img 
                  src={userAvatar} 
                  alt="Google User Avatar" 
                  className="size-7 rounded-lg object-cover border border-slate-100" 
                />
              ) : (
                <div className="flex size-7 items-center justify-center rounded-lg bg-[#0F172A] text-white font-bold text-xs">
                  <UserIcon className="size-4" />
                </div>
              )}
              <span className="max-w-[100px] truncate font-sans text-xs font-semibold text-[#0F172A]">
                {user?.user_metadata?.full_name || user?.user_metadata?.name || user?.email?.split('@')[0]}
              </span>
            </button>

            {/* Conversation Settings Menu (Positioned at far right) */}
            <div className="relative">
              <button
                onClick={() => setSettingsOpen(!settingsOpen)}
                title="Cài đặt hội thoại & Đăng xuất"
                className={`rounded-lg border p-2 cursor-pointer ${
                  isDark ? 'border-slate-800 text-slate-300 hover:bg-slate-800' : 'border-slate-200 text-slate-600 hover:bg-slate-100'
                }`}
              >
                <Settings className="size-4" />
              </button>

              {settingsOpen && (
                <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-3 shadow-2xl font-sans text-xs text-[#0F172A] z-50 editorial-rise">
                  <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 pb-2 border-b border-slate-100 flex items-center justify-between">
                    <span>Cài đặt Cuộc trò chuyện</span>
                    <button
                      onClick={() => setIsNightMode(!isNightMode)}
                      title="Toggle Night Mode"
                      className="p-1 text-slate-500 hover:text-[#2563EB]"
                    >
                      {isNightMode ? <Sun className="size-3.5 text-amber-500" /> : <Moon className="size-3.5" />}
                    </button>
                  </div>

                  <div className="py-2 space-y-1">
                    {/* Rename */}
                    <button
                      onClick={() => {
                        setNewTitleInput(currentThread?.title || '');
                        setIsRenaming(true);
                        setSettingsOpen(false);
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-100 cursor-pointer text-slate-700"
                    >
                      <Edit2 className="size-4 text-slate-500" />
                      <span>Đổi tên cuộc trò chuyện</span>
                    </button>

                    {/* Pin */}
                    <button
                      onClick={() => {
                        handleTogglePin();
                        setSettingsOpen(false);
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-100 cursor-pointer text-slate-700"
                    >
                      <Pin className="size-4 text-amber-500" />
                      <span>{currentThread?.isPinned ? 'Bỏ ghim trò chuyện' : 'Ghim lên đầu danh sách'}</span>
                    </button>

                    {/* Change Theme Background */}
                    <div className="px-2.5 py-2">
                      <div className="flex items-center gap-1.5 font-semibold text-slate-600 mb-2">
                        <Palette className="size-4 text-[#2563EB]" />
                        <span>Đổi Ảnh Nền / Theme</span>
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px]">
                        <button
                          onClick={() => handleChangeTheme('default')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'default' ? 'border-[#2563EB] bg-[#2563EB]/10 font-bold' : 'border-slate-200'}`}
                        >
                          Clean Slate
                        </button>
                        <button
                          onClick={() => handleChangeTheme('dark')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'dark' ? 'border-[#2563EB] bg-[#0F172A] text-white font-bold' : 'border-slate-200 bg-slate-900 text-white'}`}
                        >
                          Dark Slate
                        </button>
                        <button
                          onClick={() => handleChangeTheme('ivory')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'ivory' ? 'border-[#2563EB] bg-[#FBF9F5] font-bold' : 'border-slate-200 bg-[#FBF9F5]'}`}
                        >
                          Warm Ivory
                        </button>
                        <button
                          onClick={() => handleChangeTheme('grid')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'grid' ? 'border-[#2563EB] bg-slate-100 font-bold' : 'border-slate-200'}`}
                        >
                          Grid Pattern
                        </button>
                      </div>
                    </div>

                    {/* Delete Thread */}
                    <button
                      onClick={handleDeleteCurrent}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-red-600 hover:bg-red-50 cursor-pointer font-medium border-t border-slate-100 mt-1"
                    >
                      <Trash2 className="size-4" />
                      <span>Xóa cuộc trò chuyện này</span>
                    </button>

                    {/* Sign Out Button in Settings */}
                    <button
                      onClick={() => {
                        setSettingsOpen(false);
                        signOut();
                        navigate('/');
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-slate-700 hover:bg-slate-100 cursor-pointer font-medium border-t border-slate-100 mt-1"
                    >
                      <LogOut className="size-4 text-slate-500" />
                      <span>Đăng xuất tài khoản</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Legal Warning Header Banner */}
        <Legal_disclaimer compact />

        {/* MESSAGES / CHAT CONTAINER */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
          {/* EMPTY STATE: SUGGESTED QUESTIONS CARDS HARMONIZED FOR ALL THEMES */}
          {(!currentThread || currentThread.messages.length === 0) && (
            <div className="mx-auto max-w-3xl pt-6 pb-12">
              <div className="text-center">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[#2563EB]/10 border border-[#2563EB]/20 p-3">
                  <img src="/sparkles.png" alt="Sparkles" className="size-full object-contain" />
                </div>
                <h2 className="mt-4 font-display text-3xl uppercase tracking-tight">
                  Trợ lý Pháp luật Việt Nam
                </h2>
                <p className={`mt-2 text-sm max-w-md mx-auto ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                  Đặt câu hỏi bằng tiếng Việt để tra cứu căn cứ pháp lý, hiệu lực văn bản và phương án giải quyết vụ việc.
                </p>
              </div>

              {/* 4 SUGGESTED QUESTIONS CARDS WITH CONSISTENT THEME STYLING */}
              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendPrompt(q.prompt)}
                    className={`group flex flex-col justify-between rounded-xl border p-5 text-left transition-all hover:border-[#2563EB] hover:shadow-md cursor-pointer ${
                      isDark
                        ? 'border-slate-800 bg-slate-900 text-white hover:bg-slate-800'
                        : activeTheme === 'ivory'
                        ? 'border-amber-200/70 bg-white text-[#0F172A]'
                        : 'border-slate-200 bg-white text-[#0F172A]'
                    }`}
                  >
                    <div>
                      <span className={`inline-block rounded-md px-2 py-0.5 font-mono text-[10px] font-semibold text-[#2563EB] ${
                        isDark ? 'bg-slate-800' : 'bg-slate-100'
                      }`}>
                        {q.category}
                      </span>
                      <h4 className="mt-2 font-bold text-sm group-hover:text-[#2563EB]">
                        {q.title}
                      </h4>
                      <p className={`mt-1 text-xs line-clamp-2 leading-relaxed ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
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

          {/* CHAT MESSAGES LIST WITH USER GOOGLE PROFILE AVATAR */}
          {currentThread?.messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-4 max-w-4xl mx-auto ${
                msg.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.sender === 'assistant' && (
                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white overflow-hidden p-0.5 shadow-xs">
                  <img src="/logo.png" alt="Logo" className="size-full object-contain" />
                </div>
              )}

              <div className={`flex flex-col max-w-[85%] ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`font-mono text-[10px] ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    {msg.sender === 'user' ? (user?.user_metadata?.full_name || user?.user_metadata?.name || 'Bạn') : 'Trợ lý LƯU HÀNH'} · {msg.timestamp}
                  </span>
                </div>

                <div
                  className={`rounded-2xl px-5 py-4 text-sm leading-relaxed shadow-xs ${
                    msg.sender === 'user'
                      ? 'bg-[#0F172A] text-white font-medium rounded-tr-none'
                      : isDark
                      ? 'bg-slate-900 border border-slate-800 text-white rounded-tl-none'
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
                        /* DYNAMIC TYPING INDICATOR */
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

              {/* USER AVATAR (LOAD GOOGLE PROFILE PICTURE OR SUPABASE STORAGE AVATAR) */}
              {msg.sender === 'user' && (
                userAvatar ? (
                  <img 
                    src={userAvatar} 
                    alt="User Profile Avatar" 
                    className="size-9 shrink-0 rounded-lg object-cover border border-slate-300 shadow-xs cursor-pointer" 
                    title={user?.email}
                    onClick={() => setProfileModalOpen(true)}
                  />
                ) : (
                  <div 
                    onClick={() => setProfileModalOpen(true)}
                    className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[#0F172A] text-white font-bold text-sm cursor-pointer"
                  >
                    <UserIcon className="size-5" />
                  </div>
                )
              )}
            </div>
          ))}

          <div ref={messagesEndRef} />
        </div>

        {/* INPUT FORM CONTAINER WITH THEME HARMONIZATION */}
        <div className={`border-t p-4 md:px-6 transition-colors ${
          isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'
        }`}>
          <div className="mx-auto max-w-4xl">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendPrompt();
              }}
              className={`relative flex items-center rounded-xl border-2 p-2 transition-all shadow-xs ${
                isDark 
                  ? 'bg-slate-800 border-slate-700 text-white focus-within:border-[#2563EB]' 
                  : 'bg-white border-slate-300 text-[#0F172A] focus-within:border-[#2563EB] focus-within:ring-2 focus-within:ring-[#2563EB]/20'
              }`}
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
                className="flex-1 resize-none bg-transparent px-3 py-2 text-sm placeholder-slate-400 focus:outline-none max-h-32"
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

      {/* Profile Avatar Upload Modal */}
      <Profile_modal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />
    </div>
  );
};
