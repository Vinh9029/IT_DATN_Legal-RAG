import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Brand_mark } from '@/components/Brand_mark';
import { Button } from '@/components/ui/button';
import { Legal_disclaimer } from '@/components/Legal_disclaimer';
import { Status_badge } from '@/components/Status_badge';
import { Thinking_indicator } from '@/components/Thinking_indicator';
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
  deleteThread,
  deleteMessageFromThread,
  createOrGetBranch,
  addMessageToBranch,
  updateBranchMessages
} from '@/lib/session-store';
import type { ChatMessage, ChatThread, VerboseRAGInfo, SubThreadItem } from '@/lib/session-store';
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
  Terminal, 
  ChevronDown, 
  ChevronRight, 
  Database, 
  Clock, 
  Sparkles, 
  GitBranch, 
  Maximize2, 
  Minimize2, 
  X, 
  CornerDownRight 
} from 'lucide-react';


export const Assistant: React.FC = () => {
  const { threadId } = useParams<{ threadId?: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();


  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [currentThread, setCurrentThread] = useState<ChatThread | null>(null);
  const [inputQuery, setInputQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarRenameId, setSidebarRenameId] = useState<string | null>(null);
  const [sidebarRenameValue, setSidebarRenameValue] = useState('');

  // Settings & Theme & Verbose Mode states
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [isNightMode, setIsNightMode] = useState(false);
  const [activeTheme, setActiveTheme] = useState<'default' | 'dark' | 'ivory' | 'grid'>('default');
  const [isRenaming, setIsRenaming] = useState(false);
  const [newTitleInput, setNewTitleInput] = useState('');
  
  // Verbose Developer Mode state
  const [verboseMode, setVerboseMode] = useState<boolean>(() => {
    return localStorage.getItem('rag_verbose_mode') === 'true';
  });
  const [expandedVerboseMsgId, setExpandedVerboseMsgId] = useState<string | null>(null);

  // Right Panel / Branch states (Sub-thread for AI response)
  const [activeBranchMsgId, setActiveBranchMsgId] = useState<string | null>(null);
  const [branchInput, setBranchInput] = useState('');
  const [isBranchGenerating, setIsBranchGenerating] = useState(false);
  const [rightPanelWidth, setRightPanelWidth] = useState<number>(400); // 1/3 màn hình
  const [isPanelExpanded, setIsPanelExpanded] = useState<boolean>(false);
  const isResizingRef = useRef(false);
  const branchAbortControllerRef = useRef<AbortController | null>(null);
  const branchMessagesEndRef = useRef<HTMLDivElement>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const creatingThreadRef = useRef(false);

  // Chỉ tự cuộn theo chữ đang sinh khi người dùng đang ở gần cuối; kéo lên đọc thì thôi bám
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const branchScrollRef = useRef<HTMLDivElement>(null);
  const stickMainRef = useRef(true);
  const stickBranchRef = useRef(true);
  const isNearBottom = (el: HTMLElement) => el.scrollHeight - el.scrollTop - el.clientHeight < 80;

  const userAvatar = user?.user_metadata?.avatar_url || user?.user_metadata?.picture;
  // Chat rỗng không hiện trong lịch sử, chỉ chat đã có tin nhắn
  const visibleThreads = threads.filter((t) => t.messages.length > 0);

  const toggleVerboseMode = () => {
    const nextVal = !verboseMode;
    setVerboseMode(nextVal);
    localStorage.setItem('rag_verbose_mode', String(nextVal));
  };

  useEffect(() => {
    const el = chatScrollRef.current;
    if (el && stickMainRef.current) el.scrollTop = el.scrollHeight;
  }, [currentThread?.messages, isGenerating]);

  useEffect(() => {
    stickMainRef.current = true;
  }, [threadId]);

  // Listener kéo rê thay đổi độ rộng Right Panel (Drag-to-resize)
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      const newWidth = window.innerWidth - e.clientX;
      if (newWidth >= 320 && newWidth <= window.innerWidth * 0.75) {
        setRightPanelWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        document.body.style.cursor = 'default';
        document.body.style.userSelect = 'auto';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  useEffect(() => {
    const el = branchScrollRef.current;
    if (el && stickBranchRef.current) el.scrollTop = el.scrollHeight;
  }, [activeBranchMsgId, currentThread?.messages, isBranchGenerating]);

  useEffect(() => {
    stickBranchRef.current = true;
  }, [activeBranchMsgId]);


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

  const handleDeleteMessage = (msgId: string) => {
    if (!currentThread) return;
    const updated = deleteMessageFromThread(currentThread.id, msgId);
    if (updated) {
      setCurrentThread({ ...updated });
      setThreads(getThreads());
      if (activeBranchMsgId === msgId) {
        setActiveBranchMsgId(null);
      }
    }
  };

  const handleOpenBranch = (msg: ChatMessage) => {
    if (!currentThread) return;
    createOrGetBranch(currentThread.id, msg.id, msg.content);
    setActiveBranchMsgId(msg.id);
    setCurrentThread({ ...currentThread });
    setThreads(getThreads());
  };

  const handleSendBranchPrompt = async () => {
    if (!branchInput.trim() || !activeBranchMsgId || !currentThread || isBranchGenerating) return;
    const query = branchInput.trim();
    setBranchInput('');
    stickBranchRef.current = true;

    const userSubMsg: SubThreadItem = {
      id: 'submsg-user-' + Date.now(),
      sender: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
    };

    addMessageToBranch(currentThread.id, activeBranchMsgId, userSubMsg);
    setCurrentThread({ ...currentThread });
    setThreads(getThreads());

    const aiSubMsgId = 'submsg-ai-' + Date.now();
    const initialAiSubMsg: SubThreadItem = {
      id: aiSubMsgId,
      sender: 'assistant',
      content: '',
      timestamp: new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }),
      isStreaming: true
    };

    addMessageToBranch(currentThread.id, activeBranchMsgId, initialAiSubMsg);
    setCurrentThread({ ...currentThread });
    setIsBranchGenerating(true);

    branchAbortControllerRef.current = new AbortController();

    const parentMsg = currentThread.messages.find(m => m.id === activeBranchMsgId);
    const contextPrompt = `[Ngữ cảnh phản hồi pháp lý: "${parentMsg?.content.substring(0, 300)}..."]\n\nCâu hỏi tiếp nối: ${query}`;

    await streamLegalAnswer(
      contextPrompt,
      {
        onChunk: (chunkText) => {
          const currentMsg = currentThread.messages.find(m => m.id === activeBranchMsgId);
          if (currentMsg?.branch) {
            const updated = currentMsg.branch.messages.map(m => 
              m.id === aiSubMsgId ? { ...m, content: chunkText, isStreaming: true } : m
            );
            updateBranchMessages(currentThread.id, activeBranchMsgId, updated);
            setCurrentThread({ ...currentThread });
          }
        },
        onComplete: (fullText) => {
          const currentMsg = currentThread.messages.find(m => m.id === activeBranchMsgId);
          if (currentMsg?.branch) {
            const updated = currentMsg.branch.messages.map(m => 
              m.id === aiSubMsgId ? { ...m, content: fullText, isStreaming: false } : m
            );
            updateBranchMessages(currentThread.id, activeBranchMsgId, updated);
            setCurrentThread({ ...currentThread });
            setThreads(getThreads());
          }
          setIsBranchGenerating(false);
        },
        onError: (err) => {
          const currentMsg = currentThread.messages.find(m => m.id === activeBranchMsgId);
          if (currentMsg?.branch) {
            const updated = currentMsg.branch.messages.map(m => 
              m.id === aiSubMsgId ? { ...m, content: `⚠️ Lỗi: ${err.message}`, isStreaming: false } : m
            );
            updateBranchMessages(currentThread.id, activeBranchMsgId, updated);
            setCurrentThread({ ...currentThread });
          }
          setIsBranchGenerating(false);
        }
      },
      branchAbortControllerRef.current.signal
    );
  };

  const handleStopBranchGeneration = () => {
    if (branchAbortControllerRef.current) {
      branchAbortControllerRef.current.abort();
      setIsBranchGenerating(false);
    }
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
    stickMainRef.current = true;
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
        onVerboseInfo: (info: VerboseRAGInfo) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, verboseInfo: info } : m
          );
          setCurrentThread(prev => prev ? { ...prev, messages: [...currentMessages] } : null);
        },
        onChunk: (chunkText) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, content: chunkText, isStreaming: true } : m
          );
          setCurrentThread(prev => prev ? { ...prev, messages: [...currentMessages] } : null);
        },
        onComplete: (fullText, verboseInfo) => {
          currentMessages = currentMessages.map(m => 
            m.id === assistantMsgId ? { ...m, content: fullText, isStreaming: false, verboseInfo: verboseInfo || m.verboseInfo } : m
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
  const activeBranchMsg = currentThread?.messages.find(m => m.id === activeBranchMsgId);

  return (
    <div className={`flex h-screen overflow-hidden ${isDark ? 'dark' : ''}`}>

      {/* SIDEBAR - LEFT PANEL WITH CLOSE/EXPAND FEATURE */}
      <aside 
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 transition-all duration-300 md:static ${
          sidebarCollapsed ? 'w-0 overflow-hidden border-none opacity-0' : 'w-72 opacity-100'
        } ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        {/* Sidebar Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-200 dark:border-slate-800 px-4">
          <Brand_mark />
          <button 
            onClick={() => setSidebarCollapsed(true)} 
            title="Thu gọn Sidebar"
            className="hidden md:flex rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200 cursor-pointer"
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
        <div className="p-4 border-b border-slate-100 dark:border-slate-800">
          <Button
            variant="accent"
            size="md"
            onClick={handleNewThread}
            className="w-full justify-center gap-2 text-sm font-semibold uppercase tracking-wide"
          >
            <Plus className="size-4" />
            <span>Cuộc trò chuyện mới</span>
          </Button>
        </div>

        {/* Thread History List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="px-2 py-1 text-xs uppercase tracking-wide text-slate-400 flex items-center justify-between">
            <span>Lịch sử trò chuyện ({visibleThreads.length})</span>
          </div>

          {visibleThreads.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-400">
              Chưa có cuộc trò chuyện nào.
            </div>
          ) : (
            visibleThreads.map((t) => {
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
                      : 'text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                  }`}
                  title="Nhấp đúp để đổi tên"
                >
                  <MessageSquare className={`size-4 shrink-0 ${isActive ? 'text-blue-300' : 'text-slate-400'}`} />
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
                    <div className="flex items-center justify-between mt-0.5">
                      <span className={`font-mono text-[11px] ${isActive ? 'text-slate-300' : 'text-slate-400'}`}>
                        {t.createdAt}
                      </span>
                      {t.messages.some(m => m.branch && m.branch.messages.length > 0) && (
                        <span className={`flex items-center gap-0.5 font-mono text-[11px] ${isActive ? 'text-blue-200' : 'text-[#2563EB]'}`} title="Cuộc trò chuyện có nhánh thảo luận con">
                          <GitBranch className="size-2.5" />
                          <span>{t.messages.filter(m => m.branch && m.branch.messages.length > 0).length}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Sidebar Footer */}
        <div className="border-t border-slate-200 p-4 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
          <Link to="/" className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-[#2563EB] dark:hover:text-blue-400">
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
              className="md:hidden rounded-md border border-slate-200 p-2 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <MessageSquare className="size-5" />
            </button>

            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-xl border border-slate-200 dark:border-slate-700 bg-white overflow-hidden p-0.5 shadow-xs">
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
                      <Button size="sm" variant="accent" onClick={handleRenameSubmit} className="h-6 px-2 text-[12px]">
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
                <p className="text-xs text-[#2563EB] dark:text-blue-400">Online · RAG Vietnamese Law Engine</p>
              </div>
            </div>
          </div>

          {/* Action Toolbar: User Profile Avatar + Rearranged Settings Menu at far right */}
          <div className="flex items-center gap-3">
            {/* User Profile Avatar (Opens Profile Modal) */}
            <button
              onClick={() => setProfileModalOpen(true)}
              title="Quản lý Hồ sơ User Avatar"
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1 pr-3 shadow-xs dark:border-slate-700 dark:bg-slate-800 hover:border-[#2563EB] transition-colors cursor-pointer"
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
              <span className="max-w-[100px] truncate font-sans text-xs font-semibold text-[#0F172A] dark:text-slate-100">
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
                <div className="absolute right-0 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-3 shadow-2xl font-sans text-sm text-[#0F172A] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 z-50 editorial-rise">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-400 px-2 pb-2 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
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
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-100 cursor-pointer text-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      <Edit2 className="size-4 text-slate-500 dark:text-slate-400" />
                      <span>Đổi tên cuộc trò chuyện</span>
                    </button>

                    {/* Pin */}
                    <button
                      onClick={() => {
                        handleTogglePin();
                        setSettingsOpen(false);
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-slate-100 cursor-pointer text-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      <Pin className="size-4 text-amber-500" />
                      <span>{currentThread?.isPinned ? 'Bỏ ghim trò chuyện' : 'Ghim lên đầu danh sách'}</span>
                    </button>

                    {/* Verbose / Developer Mode Toggle */}
                    <div className="flex items-center justify-between px-2.5 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/60 rounded-lg border-b border-slate-100 dark:border-slate-800">
                      <div className="flex items-center gap-2">
                        <Terminal className="size-4 text-[#2563EB]" />
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-slate-100 text-sm">Verbose Mode</p>
                          <p className="text-xs text-slate-400">Hiển thị RAG Top-K docs</p>
                        </div>
                      </div>
                      <button
                        onClick={toggleVerboseMode}
                        className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                          verboseMode ? 'bg-[#2563EB]' : 'bg-slate-300 dark:bg-slate-600'
                        }`}
                      >
                        <span
                          className={`pointer-events-none inline-block size-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                            verboseMode ? 'translate-x-4' : 'translate-x-0'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Change Theme Background */}
                    <div className="px-2.5 py-2">
                      <div className="flex items-center gap-1.5 font-semibold text-slate-600 dark:text-slate-300 mb-2">
                        <Palette className="size-4 text-[#2563EB]" />
                        <span>Đổi Ảnh Nền / Theme</span>
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 text-xs">
                        <button
                          onClick={() => handleChangeTheme('default')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'default' ? 'border-[#2563EB] bg-[#2563EB]/10 font-bold' : 'border-slate-200 bg-[#F8FAFC] text-[#0F172A] dark:border-slate-700'}`}
                        >
                          Clean Slate
                        </button>
                        <button
                          onClick={() => handleChangeTheme('dark')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'dark' ? 'border-[#2563EB] ring-1 ring-[#2563EB] bg-[#0F172A] text-white font-bold' : 'border-slate-200 bg-slate-900 text-white dark:border-slate-700'}`}
                        >
                          Dark Slate
                        </button>
                        <button
                          onClick={() => handleChangeTheme('ivory')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'ivory' ? 'border-[#2563EB] bg-[#FBF9F5] text-[#0F172A] font-bold' : 'border-slate-200 bg-[#FBF9F5] text-[#0F172A] dark:border-slate-700'}`}
                        >
                          Warm Ivory
                        </button>
                        <button
                          onClick={() => handleChangeTheme('grid')}
                          className={`rounded border p-1.5 text-center ${activeTheme === 'grid' ? 'border-[#2563EB] bg-slate-100 text-[#0F172A] font-bold' : 'border-slate-200 bg-white text-[#0F172A] dark:border-slate-700'}`}
                        >
                          Grid Pattern
                        </button>
                      </div>
                    </div>

                    {/* Delete Thread */}
                    <button
                      onClick={handleDeleteCurrent}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 cursor-pointer font-medium border-t border-slate-100 dark:border-slate-800 mt-1"
                    >
                      <Trash2 className="size-4" />
                      <span>Xóa cuộc trò chuyện này</span>
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
        <div
          ref={chatScrollRef}
          onScroll={(e) => { stickMainRef.current = isNearBottom(e.currentTarget); }}
          className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6"
        >
          {/* EMPTY STATE: SUGGESTED QUESTIONS CARDS HARMONIZED FOR ALL THEMES */}
          {(!currentThread || currentThread.messages.length === 0) && (
            <div className="mx-auto max-w-3xl pt-6 pb-12">
              <div className="text-center">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-[#2563EB]/10 border border-[#2563EB]/20 p-3">
                  <img src="/sparkles.png" alt="Sparkles" className="size-full object-contain" />
                </div>
                <h2 className="mt-4 font-display text-2xl uppercase tracking-tight">
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
                      <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold text-[#2563EB] ${
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
                    <div className="mt-4 flex items-center gap-1 text-xs font-medium text-[#2563EB]">
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
              className={`group relative flex gap-4 max-w-4xl mx-auto ${
                msg.sender === 'user' ? 'justify-end' : 'justify-start'
              }`}
            >
              {msg.sender === 'assistant' && (
                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white overflow-hidden p-0.5 shadow-xs">
                  <img src="/logo.png" alt="Logo" className="size-full object-contain" />
                </div>
              )}

              <div className={`flex flex-col max-w-[85%] ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div className="flex items-center justify-between w-full gap-2 mb-1 px-1">
                  <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    {msg.sender === 'user' ? (user?.user_metadata?.full_name || user?.user_metadata?.name || 'Bạn') : 'Trợ lý LƯU HÀNH'} · {msg.timestamp}
                  </span>

                  {/* Nút Delete ở tận cùng bên phải từng card */}
                  <button
                    onClick={() => handleDeleteMessage(msg.id)}
                    title="Xóa tin nhắn này"
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-slate-400 hover:text-red-500 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>


                <div
                  className={`rounded-2xl px-5 py-4 text-base leading-relaxed shadow-xs ${
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
                    <div className={msg.isStreaming && msg.content ? 'typing-cursor' : ''}>
                      {msg.content ? (
                        renderMarkdownContent(msg.content)
                      ) : (
                        /* DYNAMIC TYPING INDICATOR */
                        <Thinking_indicator className="text-sm" />
                      )}

                      {/* VERBOSE DEVELOPER MODE ACCORDION */}
                      {verboseMode && msg.verboseInfo && (
                        <div className="mt-4 pt-3 border-t border-slate-200/60 dark:border-slate-800">
                          <button
                            onClick={() => {
                              setExpandedVerboseMsgId(expandedVerboseMsgId === msg.id ? null : msg.id);
                            }}
                            className="flex w-full items-center justify-between rounded-lg bg-slate-100/80 dark:bg-slate-800/80 px-3 py-2 font-mono text-xs font-semibold text-[#2563EB] hover:bg-slate-200/80 dark:hover:bg-slate-700/80 transition-colors cursor-pointer"
                          >
                            <div className="flex items-center gap-2">
                              <Terminal className="size-3.5" />
                              <span>Developer Verbose Mode · RAG Pipeline Insights</span>
                              {msg.verboseInfo.topKDocs && (
                                <span className="rounded bg-[#2563EB]/10 px-1.5 py-0.5 text-[12px]">
                                  {msg.verboseInfo.topKDocs.length} Docs Retrieved
                                </span>
                              )}
                              {msg.verboseInfo.timeTaken && (
                                <span className="flex items-center gap-1 text-[12px] text-slate-500 dark:text-slate-400">
                                  <Clock className="size-3" />
                                  {msg.verboseInfo.timeTaken.toFixed(3)}s
                                </span>
                              )}
                            </div>
                            {expandedVerboseMsgId === msg.id ? (
                              <ChevronDown className="size-4" />
                            ) : (
                              <ChevronRight className="size-4" />
                            )}
                          </button>

                          {expandedVerboseMsgId === msg.id && (
                            <div className="mt-2 space-y-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-3.5 text-xs font-sans">
                              {/* Query Evolution */}
                              {msg.verboseInfo.evolvedQuery && (
                                <div className="space-y-1">
                                  <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-amber-600 dark:text-amber-400">
                                    <Sparkles className="size-3.5" />
                                    <span>Stage 1: Query Evolution (WizardLM Rewriter)</span>
                                  </div>
                                  <div className="rounded-md border border-amber-200/60 bg-amber-50/50 dark:bg-amber-950/30 p-2.5 text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                                    {msg.verboseInfo.evolvedQuery}
                                  </div>
                                </div>
                              )}

                              {/* Stage Timings */}
                              {msg.verboseInfo.stageTimings && (
                                <div className="grid grid-cols-3 gap-2 font-mono text-[12px]">
                                  <div className="rounded border border-slate-200 dark:border-slate-800 p-2 bg-white dark:bg-slate-900 text-center">
                                    <p className="text-slate-400">1. Query Evolver</p>
                                    <p className="font-bold text-[#2563EB] mt-0.5">{msg.verboseInfo.stageTimings.queryEvolution?.toFixed(3)}s</p>
                                  </div>
                                  <div className="rounded border border-slate-200 dark:border-slate-800 p-2 bg-white dark:bg-slate-900 text-center">
                                    <p className="text-slate-400">2. Hybrid RRF</p>
                                    <p className="font-bold text-[#2563EB] mt-0.5">{msg.verboseInfo.stageTimings.retrieval?.toFixed(3)}s</p>
                                  </div>
                                  <div className="rounded border border-slate-200 dark:border-slate-800 p-2 bg-white dark:bg-slate-900 text-center">
                                    <p className="text-slate-400">3. Cross-Rerank</p>
                                    <p className="font-bold text-[#2563EB] mt-0.5">{msg.verboseInfo.stageTimings.rerank?.toFixed(3)}s</p>
                                  </div>
                                </div>
                              )}

                              {/* Top-K Documents List */}
                              <div className="space-y-2">
                                <div className="flex items-center justify-between font-mono text-xs font-bold text-slate-700 dark:text-slate-300">
                                  <div className="flex items-center gap-1.5">
                                    <Database className="size-3.5 text-[#2563EB]" />
                                    <span>Stage 2 & 4: Top-K Related Documents</span>
                                  </div>
                                  <span className="text-[12px] text-slate-400 font-normal">Re-ranked by bge-reranker-large</span>
                                </div>

                                {msg.verboseInfo.topKDocs && msg.verboseInfo.topKDocs.length > 0 ? (
                                  <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                                    {msg.verboseInfo.topKDocs.map((doc, docIdx) => (
                                      <div
                                        key={doc.chunk_id || docIdx}
                                        className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 shadow-xs transition-colors hover:border-[#2563EB]/50"
                                      >
                                        <div className="flex items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-1.5 mb-1.5">
                                          <div className="flex items-center gap-2 font-mono text-xs">
                                            <span className="flex size-5 items-center justify-center rounded bg-[#2563EB] text-white font-bold text-[12px]">
                                              #{docIdx + 1}
                                            </span>
                                            <span className="font-bold text-slate-800 dark:text-slate-200">
                                              {doc.metadata?.so_hieu || doc.doc_id}
                                            </span>
                                            {doc.dieu && (
                                              <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-slate-600 dark:text-slate-300">
                                                Điều {doc.dieu}
                                              </span>
                                            )}
                                          </div>
                                          <div className="flex items-center gap-1.5 font-mono text-[12px]">
                                            <span className="text-slate-400">Rerank Score:</span>
                                            <span className="font-bold text-emerald-600 dark:text-emerald-400">
                                              {doc.score.toFixed(4)}
                                            </span>
                                          </div>
                                        </div>

                                        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed font-sans line-clamp-3">
                                          {doc.content}
                                        </p>

                                        {doc.metadata && (
                                          <div className="mt-2 flex flex-wrap gap-1.5 font-mono text-[11px] text-slate-400 border-t border-slate-100 dark:border-slate-800/80 pt-1.5">
                                            {doc.metadata.loai_van_ban && (
                                              <span className="rounded bg-slate-100 dark:bg-slate-800 px-1 py-0.5">
                                                {doc.metadata.loai_van_ban}
                                              </span>
                                            )}
                                            {doc.metadata.co_quan_ban_hanh && (
                                              <span className="rounded bg-slate-100 dark:bg-slate-800 px-1 py-0.5">
                                                {doc.metadata.co_quan_ban_hanh}
                                              </span>
                                            )}
                                            {doc.metadata.tinh_trang && (
                                              <span className={`rounded px-1 py-0.5 ${
                                                doc.metadata.tinh_trang.toLowerCase().includes('còn hiệu lực')
                                                  ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400'
                                                  : 'bg-amber-50 text-amber-600 dark:bg-amber-950/40 dark:text-amber-400'
                                              }`}>
                                                {doc.metadata.tinh_trang}
                                              </span>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-xs text-slate-400 font-mono italic">Không có tài liệu nào được trả về.</p>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* NÚT MỞ NHÁNH THẢO LUẬN RIÊNG BIỆT (SUB-THREAD BRANCH) */}

                      {!msg.isStreaming && msg.content && (
                        <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-2">
                          <button
                            onClick={() => handleOpenBranch(msg)}
                            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-all cursor-pointer ${
                              activeBranchMsgId === msg.id
                                ? 'bg-[#2563EB] text-white shadow-xs'
                                : msg.branch && msg.branch.messages.length > 0
                                ? 'bg-[#2563EB]/10 text-[#2563EB] hover:bg-[#2563EB]/20 border border-[#2563EB]/30'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                            }`}
                            title="Mở nhánh thảo luận đào sâu sang tab bên phải"
                          >
                            <GitBranch className="size-3.5" />
                            <span>
                              {msg.branch && msg.branch.messages.length > 0
                                ? `Nhánh thảo luận (${msg.branch.messages.length})`
                                : 'Mở nhánh thảo luận'}
                            </span>
                            {activeBranchMsgId === msg.id && (
                              <span className="size-1.5 rounded-full bg-emerald-300 animate-pulse ml-0.5" />
                            )}
                          </button>

                          {msg.branch && (
                            <span 
                              onClick={() => handleOpenBranch(msg)}
                              className="text-xs text-slate-400 hover:text-[#2563EB] cursor-pointer truncate max-w-[200px]"
                              title={msg.branch.title}
                            >
                              ↳ {msg.branch.title}
                            </span>
                          )}
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
                className="flex-1 resize-none bg-transparent px-3 py-2 text-base placeholder-slate-400 focus:outline-none max-h-32"
              />

              <div className="flex items-center gap-2">
                {isGenerating ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleStopGeneration}
                    className="text-red-600 border-red-200 hover:bg-red-50 text-xs"
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
                    className="gap-1.5 text-xs uppercase"
                  >
                    <span>Gửi</span>
                    <Send className="size-3.5" />
                  </Button>
                )}
              </div>
            </form>
            <p className="mt-2 text-center text-xs text-slate-400">
              LƯU HÀNH AI Trợ lý Pháp lý · Dữ liệu phản hồi được xử lý trong phiên làm việc hiện tại
            </p>
          </div>
        </div>
      </div>

      {/* RIGHT PANEL - SUB-THREAD / BRANCH DISCUSSION */}
      {activeBranchMsg && activeBranchMsg.branch && (
        <aside
          style={{ width: isPanelExpanded ? '60%' : `${rightPanelWidth}px` }}
          className={`relative flex flex-col border-l transition-all duration-150 h-full z-20 shadow-xl ${
            isDark ? 'border-slate-800 bg-slate-900 text-white' : 'border-slate-200 bg-white text-[#0F172A]'
          }`}
        >
          {/* DRAG-TO-RESIZE HANDLE */}
          {!isPanelExpanded && (
            <div
              onMouseDown={() => {
                isResizingRef.current = true;
                document.body.style.cursor = 'ew-resize';
                document.body.style.userSelect = 'none';
              }}
              className="absolute left-0 top-0 bottom-0 w-2 -ml-1 cursor-ew-resize hover:bg-[#2563EB]/80 active:bg-[#2563EB] transition-colors z-30 flex items-center justify-center group"
              title="Kéo sang trái/phải để thay đổi độ rộng tab"
            >
              <div className="w-0.5 h-8 bg-slate-300 dark:bg-slate-700 group-hover:bg-[#2563EB] rounded-full" />
            </div>
          )}

          {/* RIGHT PANEL HEADER */}
          <div className={`flex h-16 items-center justify-between border-b px-4 transition-colors ${
            isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'
          }`}>
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="flex size-7 items-center justify-center rounded-lg bg-[#2563EB]/10 text-[#2563EB] shrink-0">
                <GitBranch className="size-4" />
              </div>
              <div className="overflow-hidden">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs uppercase font-bold text-[#2563EB]">Nhánh thảo luận</span>
                  <span className="text-[12px] text-slate-400">· {activeBranchMsg.branch.messages.length} phản hồi</span>
                </div>
                <h3 className="font-bold text-xs truncate max-w-[220px]" title={activeBranchMsg.branch.title}>
                  {activeBranchMsg.branch.title}
                </h3>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsPanelExpanded(!isPanelExpanded)}
                title={isPanelExpanded ? "Thu nhỏ về 1/3" : "Mở rộng màn hình"}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer"
              >
                {isPanelExpanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
              </button>
              <button
                onClick={() => setActiveBranchMsgId(null)}
                title="Đóng nhánh thảo luận"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>
          </div>

          {/* TRÍCH ĐOẠN CÂU TRẢ LỜI GỐC (ORIGINAL CONTEXT SNIPPET) */}
          <div className="border-b border-slate-100 dark:border-slate-800/80 bg-slate-50/80 dark:bg-slate-950/40 p-3 text-xs">
            <div className="flex items-center gap-1 text-xs text-slate-400 mb-1">
              <CornerDownRight className="size-3 text-[#2563EB]" />
              <span>Nội dung phản hồi gốc:</span>
            </div>
            <p className="line-clamp-2 text-slate-600 dark:text-slate-300 italic font-serif leading-relaxed">
              "{activeBranchMsg.branch.parentSnippet}"
            </p>
          </div>

          {/* DANH SÁCH TIN NHẮN TRONG NHÁNH CON */}
          <div
            ref={branchScrollRef}
            onScroll={(e) => { stickBranchRef.current = isNearBottom(e.currentTarget); }}
            className="flex-1 overflow-y-auto p-4 space-y-4 text-sm"
          >
            {activeBranchMsg.branch.messages.length === 0 ? (
              <div className="py-12 text-center text-slate-400 space-y-2">
                <GitBranch className="size-8 mx-auto text-slate-300 dark:text-slate-700" />
                <p className="text-xs font-semibold">Chưa có câu hỏi nào trong nhánh này.</p>
                <p className="text-xs text-slate-500">Đặt câu hỏi để làm rõ hoặc đào sâu căn cứ pháp lý ở trên.</p>
              </div>
            ) : (
              activeBranchMsg.branch.messages.map((subMsg) => (
                <div
                  key={subMsg.id}
                  className={`flex flex-col ${subMsg.sender === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <span className="text-xs text-slate-400 mb-1 px-1">
                    {subMsg.sender === 'user' ? (user?.user_metadata?.full_name || user?.user_metadata?.name || 'Bạn') : 'Trợ lý LƯU HÀNH'} · {subMsg.timestamp}
                  </span>
                  <div
                    className={`rounded-xl px-3.5 py-2.5 leading-relaxed shadow-xs max-w-[90%] ${
                      subMsg.sender === 'user'
                        ? 'bg-[#0F172A] text-white rounded-tr-none'
                        : isDark
                        ? 'bg-slate-800 border border-slate-700 text-white rounded-tl-none'
                        : 'bg-white border border-slate-200 text-[#0F172A] rounded-tl-none'
                    }`}
                  >
                    {subMsg.sender === 'user' ? (
                      <p className="whitespace-pre-wrap">{subMsg.content}</p>
                    ) : (
                      <div className={subMsg.isStreaming && subMsg.content ? 'typing-cursor' : ''}>
                        {subMsg.content ? (
                          renderMarkdownContent(subMsg.content)
                        ) : (
                          <Thinking_indicator className="text-xs" />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={branchMessagesEndRef} />
          </div>

          {/* INPUT GỬI TRONG NHÁNH CON */}
          <div className={`border-t p-3 transition-colors ${
            isDark ? 'border-slate-800 bg-slate-900' : 'border-slate-200 bg-white'
          }`}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendBranchPrompt();
              }}
              className={`flex items-center rounded-xl border p-1.5 transition-all shadow-xs ${
                isDark 
                  ? 'bg-slate-800 border-slate-700 text-white focus-within:border-[#2563EB]' 
                  : 'bg-white border-slate-300 text-[#0F172A] focus-within:border-[#2563EB]'
              }`}
            >
              <textarea
                value={branchInput}
                onChange={(e) => setBranchInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendBranchPrompt();
                  }
                }}
                placeholder="Hỏi sâu thêm về nội dung này... (Enter để gửi)"
                rows={1}
                className="flex-1 resize-none bg-transparent px-2.5 py-1.5 text-sm placeholder-slate-400 focus:outline-none max-h-24"
              />

              {isBranchGenerating ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleStopBranchGeneration}
                  className="text-red-600 border-red-200 hover:bg-red-50 text-xs h-7 px-2"
                >
                  <Square className="size-3 fill-red-600" />
                  <span>Dừng</span>
                </Button>
              ) : (
                <Button
                  type="submit"
                  variant="accent"
                  size="sm"
                  disabled={!branchInput.trim()}
                  className="text-xs h-7 px-2.5 uppercase"
                >
                  <Send className="size-3" />
                </Button>
              )}
            </form>
          </div>
        </aside>
      )}

      {/* Profile Avatar Upload Modal */}
      <Profile_modal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />
    </div>
  );
};

