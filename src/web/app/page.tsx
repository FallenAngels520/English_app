'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Maximize2,
  RefreshCcw,
  RotateCcw,
  StopCircle,
  X,
  XCircle
} from 'lucide-react';
import { Sidebar } from '@/components/chat/sidebar';
import { ChatInput } from '@/components/chat/chat-input';
import { ChatMessage } from '@/components/chat/chat-message';
import { ResultPanel } from '@/components/chat/result-panel';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type {
  CachedResponseRecord,
  ChatMessage as ChatMessageType,
  Conversation,
  ConversationResult
} from '@/types/chat';
import type { WordMemoryResult } from '@/types/result';

const STORAGE_KEY = 'english-app-chat-sessions';
const ACTIVE_KEY = 'english-app-chat-active';
const STORAGE_API_BASE = (process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
const DEFAULT_SESSION_TITLE = '新会话';

const buildStorageUrl = (path: string) => `${STORAGE_API_BASE}/storage${path}`;

const generateId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).substring(2, 10);
};

const createConversation = (): Conversation => {
  const now = new Date().toISOString();
  return {
    id: generateId(),
    title: DEFAULT_SESSION_TITLE,
    createdAt: now,
    updatedAt: now,
    messages: [],
    finalOutputs: []
  };
};

const normalizeConversation = (
  session: Partial<Conversation> & { finalOutput?: WordMemoryResult | null }
): Conversation => {
  const fallback: Conversation = createConversation();
  const { finalOutput, finalOutputs, ...rest } = session;

  const normalizedOutputs: ConversationResult[] = Array.isArray(finalOutputs)
    ? finalOutputs.map((entry: any) =>
        entry && typeof entry === 'object' && 'result' in entry
          ? {
              id: entry.id ?? generateId(),
              result: entry.result as WordMemoryResult,
              createdAt: entry.createdAt ?? null,
              recordId: entry.recordId ?? null
            }
          : { id: generateId(), result: entry as WordMemoryResult, createdAt: null, recordId: null }
      )
    : finalOutput
    ? [{ id: generateId(), result: finalOutput, createdAt: new Date().toISOString(), recordId: null }]
    : [];

  return {
    ...fallback,
    ...rest,
    finalOutputs: normalizedOutputs,
    messages: session.messages ?? fallback.messages
  };
};

const createMessage = (role: ChatMessageType['role'], content = ''): ChatMessageType => ({
  id: generateId(),
  role,
  content,
  createdAt: new Date().toISOString()
});

const buildTitleFromMessages = (messages: ChatMessageType[]) => {
  const firstUser = messages.find((message) => message.role === 'user');
  if (!firstUser) return DEFAULT_SESSION_TITLE;
  const normalized = firstUser.content.replace(/\s+/g, ' ').trim();
  return normalized.length > 24 ? `${normalized.slice(0, 24)}…` : normalized || DEFAULT_SESSION_TITLE;
};

const buildFallbackImage = (word: string) => {
  const display = (word || '?').trim().charAt(0).toUpperCase() || '?';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="320" viewBox="0 0 512 320"><rect width="512" height="320" fill="#1d4ed8"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="160" fill="#ffffff" font-family="Arial, Helvetica, sans-serif">${display}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

const getCardImageUrl = (result: WordMemoryResult) => {
  const imageUrl = result.media?.image?.url;
  if (imageUrl) return imageUrl;
  const fallbackWord = result.word_block?.word ?? '';
  return buildFallbackImage(fallbackWord);
};

type MessagesUpdater = ChatMessageType[] | ((messages: ChatMessageType[]) => ChatMessageType[]);

interface AgentResponse {
  reply_text?: string;
  final_output?: WordMemoryResult | null;
}

type RegenStatus = 'idle' | 'loading' | 'success' | 'error';

interface ImagePreviewState {
  src: string;
  alt: string;
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [initialized, setInitialized] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [showLibrary, setShowLibrary] = useState(false);
  const [libraryIndex, setLibraryIndex] = useState(0);
  const [detailResult, setDetailResult] = useState<WordMemoryResult | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [regenStatus, setRegenStatus] = useState<RegenStatus>('idle');
  const [imagePreview, setImagePreview] = useState<ImagePreviewState | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);
  const regenResetRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearRegenStatus = useCallback(() => {
    if (regenResetRef.current) {
      clearTimeout(regenResetRef.current);
      regenResetRef.current = null;
    }
    setRegenStatus('idle');
  }, []);

  const scheduleRegenStatusReset = useCallback(() => {
    if (regenResetRef.current) {
      clearTimeout(regenResetRef.current);
    }
    regenResetRef.current = setTimeout(() => {
      setRegenStatus('idle');
      regenResetRef.current = null;
    }, 2500);
  }, []);

  const activeSession = useMemo(() => sessions.find((session) => session.id === activeId) ?? null, [sessions, activeId]);
  const libraryItems = useMemo(() => {
    return sessions
      .flatMap((session) =>
        session.finalOutputs.map((output) => ({
          sessionId: session.id,
          entryId: output.id,
          recordId: output.recordId,
          createdAt: output.createdAt ?? session.updatedAt ?? '',
          result: output.result
        }))
      )
      .sort((a, b) => {
        const aTime = a.createdAt ? new Date(a.createdAt).getTime() : 0;
        const bTime = b.createdAt ? new Date(b.createdAt).getTime() : 0;
        return bTime - aTime;
      });
  }, [sessions]);

  useEffect(
    () => () => {
      if (regenResetRef.current) {
        clearTimeout(regenResetRef.current);
      }
    },
    []
  );

  useEffect(() => {
    if (!showLibrary) return;
    if (libraryIndex >= libraryItems.length) {
      setLibraryIndex(Math.max(libraryItems.length - 1, 0));
    }
  }, [showLibrary, libraryIndex, libraryItems.length]);

  const handleOpenLibrary = () => {
    if (libraryItems.length === 0) return;
    setLibraryIndex(0);
    setShowLibrary(true);
  };

  const handleCloseLibrary = () => setShowLibrary(false);

  const handlePrevLibrary = () => {
    setLibraryIndex((prev) => Math.max(prev - 1, 0));
  };

  const handleNextLibrary = () => {
    setLibraryIndex((prev) => Math.min(prev + 1, Math.max(libraryItems.length - 1, 0)));
  };

  const handleViewDetail = useCallback(
    async (item: (typeof libraryItems)[number]) => {
      if (!item) return;
      if (!item.recordId) {
        setDetailResult(item.result);
        setDetailVisible(true);
        setDetailError(null);
        return;
      }
      setDetailLoading(true);
      setDetailError(null);
      try {
        const response = await fetch(
          buildStorageUrl(`/${item.sessionId}/records/${encodeURIComponent(item.recordId)}`)
        );
        if (!response.ok) {
          throw new Error('无法加载卡片详情');
        }
    const detail = (await response.json()) as CachedResponseRecord;
        const result = detail.response?.final_output;
        if (result) {
          setDetailResult(result);
          setDetailVisible(true);
        } else {
          throw new Error('无效的卡片数据');
        }
      } catch (fetchError) {
        setDetailError((fetchError as Error).message ?? '加载失败');
      } finally {
        setDetailLoading(false);
      }
    },
    [libraryItems]
  );

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setDetailResult(null);
    setDetailError(null);
  };

  const handlePreviewImage = useCallback((src: string | null | undefined, alt?: string) => {
    if (!src) return;
    setImagePreview({ src, alt: alt?.trim() || '图片预览' });
  }, []);

  const handleClosePreview = useCallback(() => setImagePreview(null), []);

  useEffect(() => {
    if (!imagePreview) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        handleClosePreview();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClosePreview, imagePreview]);

  useEffect(() => {
    if (initialized) return;
    if (typeof window === 'undefined') return;
    const storedSessions = window.localStorage.getItem(STORAGE_KEY);
    const storedActive = window.localStorage.getItem(ACTIVE_KEY);
    let parsedSessions: Conversation[] | null = null;
    if (storedSessions) {
      try {
        parsedSessions = JSON.parse(storedSessions);
      } catch (storageError) {
        console.warn('无法解析本地会话数据', storageError);
      }
    }
    const sessionsToUse = parsedSessions?.length ? parsedSessions : [createConversation()];
    const normalized = sessionsToUse.map((session) => normalizeConversation(session));
    const activeIdFromStorage = normalized.find((session) => session.id === storedActive)?.id ?? normalized[0].id;
    setSessions(normalized);
    setActiveId(activeIdFromStorage);
    setInitialized(true);
  }, [initialized]);

  useEffect(() => {
    if (!initialized || typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions, initialized]);

  useEffect(() => {
    if (!initialized || typeof window === 'undefined' || !activeId) return;
    window.localStorage.setItem(ACTIVE_KEY, activeId);
  }, [activeId, initialized]);

  useEffect(() => {
    const fetchAllStoredResults = async () => {
      try {
        const response = await fetch(buildStorageUrl('/all?limit=10'));
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as CachedResponseRecord[];
        if (!Array.isArray(data) || data.length === 0) return;
        const grouped = data.reduce<Record<string, CachedResponseRecord[]>>((acc, record) => {
          const sid = record.session_id;
          if (!sid) return acc;
          if (!acc[sid]) acc[sid] = [];
          acc[sid].push(record);
          return acc;
        }, {});
        setSessions((prev) => {
          const sessionMap = new Map(prev.map((session) => [session.id, session]));

          Object.entries(grouped).forEach(([sid, records]) => {
            const existing = sessionMap.get(sid);
            if (!existing) {
              const newSession = {
                ...createConversation(),
                id: sid,
                title: '历史会话',
                finalOutputs: records
                  .filter((record) => record.response?.final_output)
                  .map((record) => ({
                    id: record.record_id ?? record.cached_at ?? generateId(),
                    result: record.response?.final_output as WordMemoryResult,
                    createdAt: record.cached_at ?? null,
                    recordId: record.record_id ?? null
                  })),
                messages: []
              };
              sessionMap.set(sid, newSession);
              return;
            }
            const unseen = records.filter((record) => {
              const result = record.response?.final_output;
              if (!result) return false;
              const targetId = record.record_id ?? record.cached_at;
              return !existing.finalOutputs.some((existingItem) => (existingItem.recordId ?? existingItem.id) === targetId);
            });
            if (unseen.length === 0) {
              sessionMap.set(sid, existing);
              return;
            }
            const mergedFinalOutputs = [
              ...existing.finalOutputs,
              ...unseen.map((record) => ({
                id: record.record_id ?? record.cached_at ?? generateId(),
                result: record.response?.final_output as WordMemoryResult,
                createdAt: record.cached_at ?? null,
                recordId: record.record_id ?? null
              }))
            ];
            sessionMap.set(sid, { ...existing, finalOutputs: mergedFinalOutputs });
          });

          return Array.from(sessionMap.values());
        });
      } catch (storageError) {
        console.warn('Failed to load stored results', storageError);
      }
    };

    fetchAllStoredResults();
  }, []);
  const scrollToBottom = useCallback(() => {
    const container = chatContainerRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, []);

  useEffect(() => {
    const raf = requestAnimationFrame(scrollToBottom);
    return () => cancelAnimationFrame(raf);
  }, [scrollToBottom, activeSession?.id, activeSession?.messages.length, isStreaming, streamingMessageId]);

  const ensureSession = useCallback(() => {
    if (activeSession) return activeSession;
    const newSession = createConversation();
    setSessions((prev) => [newSession, ...prev]);
    setActiveId(newSession.id);
    return newSession;
  }, [activeSession]);

  const updateSessionMessages = useCallback((sessionId: string, updater: MessagesUpdater) => {
    setSessions((prev) =>
      prev.map((session) => {
        if (session.id !== sessionId) return session;
        const nextMessages = typeof updater === 'function' ? (updater as (messages: ChatMessageType[]) => ChatMessageType[])(session.messages) : updater;
        return {
          ...session,
          title:
            session.messages.length === 0 || session.title === DEFAULT_SESSION_TITLE
              ? buildTitleFromMessages(nextMessages)
              : session.title,
          messages: nextMessages,
          updatedAt: new Date().toISOString()
        };
      })
    );
  }, []);

  const runChat = useCallback(
    async (messagesPayload: ChatMessageType[], sessionId: string, assistantMessageId: string) => {
      setIsStreaming(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;
      setError(null);
      let isSuccess = false;
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId,
            messages: messagesPayload.map(({ role, content }) => ({ role, content }))
          }),
          signal: controller.signal
        });

        if (!response.ok) {
          const errorBody = (await response.json().catch(() => ({}))) as { error?: string };
          throw new Error(errorBody?.error ?? '无法生成回复');
        }

        const data: AgentResponse = await response.json();
        const reply = data?.reply_text ?? '';

        updateSessionMessages(sessionId, (messages) =>
          messages.map((message) =>
            message.id === assistantMessageId ? { ...message, content: reply, error: false } : message
          )
        );
        setSessions((prev) =>
          prev.map((session) => {
            if (session.id !== sessionId) return session;
            const nextOutputs =
              data?.final_output != null
                ? [
                    ...session.finalOutputs,
                    {
                      id: assistantMessageId,
                      result: data.final_output,
                      createdAt: new Date().toISOString(),
                      recordId: undefined
                    }
                  ]
                : session.finalOutputs;
            return {
              ...session,
              finalOutputs: nextOutputs,
              updatedAt: new Date().toISOString()
            };
          })
        );
        setPendingUserMessage(null);
        isSuccess = true;
      } catch (chatError) {
        if ((chatError as DOMException).name === 'AbortError') {
          setError('生成已停止');
        } else {
          console.error(chatError);
          setError((chatError as Error).message || '生成失败，请重试');
          updateSessionMessages(sessionId, (messages) =>
            messages.map((message) => (message.id === assistantMessageId ? { ...message, error: true } : message))
          );
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
        setStreamingMessageId(null);
      }
      return isSuccess;
    },
    [updateSessionMessages]
  );

  const sendNewMessage = useCallback(
    async (rawInput?: string) => {
      const session = ensureSession();
      const sessionId = session.id;
      const text = (rawInput ?? input).trim();
      if (!text) return;
      clearRegenStatus();

      const userMessage = createMessage('user', text);
      const assistantMessage = createMessage('assistant', '');
      const nextMessages = [...session.messages, userMessage, assistantMessage];
      setPendingUserMessage(text);
      setStreamingMessageId(assistantMessage.id);
      setInput('');
      updateSessionMessages(sessionId, nextMessages);
      await runChat([...session.messages, userMessage], sessionId, assistantMessage.id);
    },
    [clearRegenStatus, ensureSession, input, runChat, updateSessionMessages]
  );

  const replayLastUserMessage = useCallback(async () => {
    if (!activeSession || activeSession.messages.length === 0) return;
    const lastUserIndex = [...activeSession.messages].map((message, index) => ({ message, index }))
      .reverse()
      .find(({ message }) => message.role === 'user')?.index;
    if (lastUserIndex == null) return;
    const payload = activeSession.messages.slice(0, lastUserIndex + 1);
    const assistantMessage = createMessage('assistant', '');
    const updatedMessages = [...payload, assistantMessage];
    setPendingUserMessage(payload[payload.length - 1].content);
    setStreamingMessageId(assistantMessage.id);
    updateSessionMessages(activeSession.id, updatedMessages);
    if (regenResetRef.current) {
      clearTimeout(regenResetRef.current);
      regenResetRef.current = null;
    }
    setRegenStatus('loading');
    const ok = await runChat(payload, activeSession.id, assistantMessage.id);
    setRegenStatus(ok ? 'success' : 'error');
    scheduleRegenStatusReset();
  }, [activeSession, runChat, scheduleRegenStatusReset, updateSessionMessages]);

  const handleStop = () => {
    if (!abortControllerRef.current) return;
    abortControllerRef.current.abort();
    if (regenStatus === 'loading') {
      setRegenStatus('error');
      scheduleRegenStatusReset();
    }
  };

  const handleDeleteSession = (sessionId: string) => {
    setError(null);
    setPendingUserMessage(null);
    setStreamingMessageId(null);
    clearRegenStatus();
    if (abortControllerRef.current && activeId === sessionId) {
      abortControllerRef.current.abort();
    }
    setSessions((prev) => {
      const filtered = prev.filter((session) => session.id !== sessionId);
      if (filtered.length === 0) {
        const newSession = createConversation();
        setActiveId(newSession.id);
        return [newSession];
      }
      if (activeId === sessionId) {
        setActiveId(filtered[0].id);
      }
      return filtered;
    });
  };

  const handleCreateSession = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const newSession = createConversation();
    setSessions((prev) => [newSession, ...prev]);
    setActiveId(newSession.id);
    setInput('');
    setError(null);
    setPendingUserMessage(null);
    setStreamingMessageId(null);
    clearRegenStatus();
  };

  const lastUserMessage = useMemo(() => {
    if (!activeSession) return null;
    return [...activeSession.messages].reverse().find((message) => message.role === 'user') ?? null;
  }, [activeSession]);

  const finalOutputs = activeSession?.finalOutputs ?? [];

  if (!initialized) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          <p>加载中…</p>
        </div>
      </main>
    );
  }

  return (
    <>
      <main className="flex min-h-screen bg-background text-foreground">
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={handleCreateSession}
          onDelete={handleDeleteSession}
          onOpenLibrary={handleOpenLibrary}
          hasLibraryItems={libraryItems.length > 0}
        />
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b px-6 py-4">
            <div className="space-y-1">
              <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">English Helper</p>
              <h1 className="text-2xl font-semibold leading-tight">English 助手</h1>
              <p className="text-sm text-muted-foreground">支持 Markdown、代码高亮与流式回复</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="secondary"
                  onClick={replayLastUserMessage}
                  size="sm"
                  className="gap-2"
                  disabled={!lastUserMessage || regenStatus === 'loading' || isStreaming}
                  type="button"
                >
                  {regenStatus === 'loading' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                  {regenStatus === 'loading' ? '生成中…' : '重新生成'}
                </Button>
                {isStreaming && (
                  <Button variant="destructive" onClick={handleStop} size="sm" className="gap-2" type="button">
                    <StopCircle className="h-4 w-4" /> 停止生成
                  </Button>
                )}
              </div>
              {regenStatus !== 'idle' && (
                <div
                  className={`flex items-center gap-1 text-xs ${
                    regenStatus === 'success'
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : regenStatus === 'error'
                      ? 'text-destructive'
                      : 'text-muted-foreground'
                  }`}
                >
                  {regenStatus === 'success' && <CheckCircle2 className="h-3.5 w-3.5" />}
                  {regenStatus === 'error' && <XCircle className="h-3.5 w-3.5" />}
                  {regenStatus === 'loading' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  <span>
                    {regenStatus === 'success'
                      ? '最新回复已生成'
                      : regenStatus === 'error'
                      ? '生成失败，请重试'
                      : '正在生成回复…'}
                  </span>
                </div>
              )}
            </div>
          </header>
          <div ref={chatContainerRef} className="chat-scroll flex flex-1 flex-col overflow-y-auto px-4 py-6">
            <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col">
              {!activeSession || activeSession.messages.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center rounded-3xl border border-dashed border-border/70 bg-card/60 px-6 py-10 text-center text-muted-foreground">
                  <RefreshCcw className="mb-4 h-10 w-10 text-primary" />
                  <p className="text-lg font-semibold text-foreground">开始新的对话</p>
                  <p className="text-sm leading-relaxed">
                    输入你的问题，按 Enter 即可发送。<br />
                    Shift+Enter 用于换行。
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-4 pb-4">
                  {activeSession.messages.map((message) => (
                    <ChatMessage key={message.id} message={message} isStreaming={streamingMessageId === message.id && isStreaming} />
                  ))}
                </div>
              )}
            </div>
          </div>
          {error && (
            <div className="border-t bg-destructive/5 px-4 py-4">
              <div className="mx-auto w-full max-w-3xl">
                <Alert variant="destructive" className="bg-transparent">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>出错了</AlertTitle>
                  <AlertDescription className="flex flex-wrap items-center gap-3 text-sm">
                    <span>{error}</span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={replayLastUserMessage}
                      className="gap-2"
                      disabled={isStreaming || regenStatus === 'loading'}
                      type="button"
                    >
                      <RefreshCcw className="h-4 w-4" /> 重试
                    </Button>
                  </AlertDescription>
                </Alert>
              </div>
            </div>
          )}
          {finalOutputs.length > 0 && (
            <div className="border-t bg-muted/20 px-4 py-4">
              <div className="mx-auto w-full max-w-3xl space-y-4">
                {finalOutputs.map((entry) => (
                  <ResultPanel key={entry.id} result={entry.result} onPreviewImage={handlePreviewImage} />
                ))}
              </div>
            </div>
          )}
          <div className="border-t bg-card/70 px-4 py-4">
            <div className="mx-auto w-full max-w-3xl space-y-2">
              <ChatInput
                value={input}
                onChange={setInput}
                placeholder="和 English 助手聊天..."
                disabled={isStreaming}
                isLoading={isStreaming}
                onSubmit={() => sendNewMessage()}
              />
              <div className="flex flex-wrap items-center justify-between text-xs text-muted-foreground">
                <span>Enter 发送 · Shift+Enter 换行</span>
                {pendingUserMessage && !isStreaming && (
                  <Button
                    variant="link"
                    size="sm"
                    onClick={replayLastUserMessage}
                    className="p-0 text-xs"
                    disabled={regenStatus === 'loading'}
                    type="button"
                  >
                    再试一次
                  </Button>
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
      {showLibrary && (
        <CardLibraryOverlay
          items={libraryItems}
          index={libraryIndex}
          onClose={handleCloseLibrary}
          onPrev={handlePrevLibrary}
          onNext={handleNextLibrary}
          onViewDetail={handleViewDetail}
          onPreviewImage={handlePreviewImage}
          detailLoading={detailLoading}
          detailError={detailError}
        />
      )}
      {detailVisible && detailResult && (
        <CardDetailModal result={detailResult} onClose={handleCloseDetail} onPreviewImage={handlePreviewImage} />
      )}
      {imagePreview && <ImagePreviewModal image={imagePreview} onClose={handleClosePreview} />}
    </>
  );
}

interface LibraryItem {
  sessionId: string;
  entryId: string;
  recordId?: string;
  createdAt?: string | null;
  result: WordMemoryResult;
}

interface CardLibraryOverlayProps {
  items: LibraryItem[];
  index: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onViewDetail: (item: LibraryItem) => void;
  onPreviewImage: (src: string | null | undefined, alt?: string) => void;
  detailLoading: boolean;
  detailError: string | null;
}

function CardLibraryOverlay({
  items,
  index,
  onClose,
  onPrev,
  onNext,
  onViewDetail,
  onPreviewImage,
  detailLoading,
  detailError
}: CardLibraryOverlayProps) {
  const current = items[index];
  const hasPrev = index > 0;
  const hasNext = index < items.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/90 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold">卡片库</h2>
          <p className="text-sm text-muted-foreground">共 {items.length} 张记忆卡片，点击卡片名称可查看详情。</p>
        </div>
        <Button variant="ghost" onClick={onClose} className="gap-2" type="button">
          <X className="h-4 w-4" /> 关闭
        </Button>
      </div>
      <div className="flex flex-1 flex-col px-4 py-6">
        {current ? (
          <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6">
            <div className="flex flex-1 flex-col gap-6 rounded-3xl border bg-card/80 p-6 shadow-2xl">
              <div className="flex flex-col items-center gap-3 text-center">
                <button
                  type="button"
                  className="text-4xl font-bold text-foreground transition hover:text-primary"
                  onClick={() => onViewDetail(current)}
                >
                  {current.result.word_block?.word ?? '未命名'}
                </button>
                {detailLoading && <p className="text-xs text-muted-foreground">正在加载完整信息…</p>}
                {detailError && <p className="text-xs text-destructive">{detailError}</p>}
              </div>
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-4">
                  <div className="relative aspect-[5/3] w-full overflow-hidden rounded-2xl border border-border bg-background">
                    <img
                      src={getCardImageUrl(current.result)}
                      alt={current.result.word_block?.word ?? 'card image'}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                    <button
                      type="button"
                      className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-background/80 px-3 py-1 text-xs font-medium text-foreground shadow ring-1 ring-border backdrop-blur"
                      onClick={() => onPreviewImage(getCardImageUrl(current.result), current.result.word_block?.word)}
                    >
                      <Maximize2 className="h-3.5 w-3.5" /> 放大查看
                    </button>
                  </div>
                  <div className="rounded-2xl bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
                    <p>生成时间：{current.createdAt ? new Date(current.createdAt).toLocaleString() : '未知'}</p>
                    <p>记录 ID：{current.recordId ?? '暂无'}</p>
                  </div>
                </div>
                <div className="space-y-4 rounded-2xl border border-border/60 bg-background/80 p-5">
                  <div>
                    <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">词义</p>
                    <p className="text-xl font-semibold">
                      {current.result.word_block?.meaning.pos && (
                        <span className="mr-2 text-muted-foreground">{current.result.word_block.meaning.pos}</span>
                      )}
                      {current.result.word_block?.meaning.cn ?? '暂无释义'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold tracking-[0.2em] text-muted-foreground">记忆提示</p>
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      {current.result.word_block?.story ?? '暂无记忆场景'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>
                第 {index + 1} / {items.length} 张
              </span>
              <div className="flex items-center gap-3">
                <Button variant="outline" size="sm" onClick={onPrev} disabled={!hasPrev} className="gap-1">
                  <ChevronLeft className="h-4 w-4" /> 上一张
                </Button>
                <Button variant="outline" size="sm" onClick={onNext} disabled={!hasNext} className="gap-1">
                  下一张 <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center text-sm text-muted-foreground">
            暂无卡片可展示。
          </div>
        )}
      </div>
    </div>
  );
}

interface CardDetailModalProps {
  result: WordMemoryResult;
  onClose: () => void;
  onPreviewImage: (src: string | null | undefined, alt?: string) => void;
}

function CardDetailModal({ result, onClose, onPreviewImage }: CardDetailModalProps) {
  if (!result) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/90 p-4">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-3xl border bg-card p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b pb-3">
          <h3 className="text-lg font-semibold">????</h3>
          <Button variant="ghost" onClick={onClose} className="gap-2" type="button">
            <X className="h-4 w-4" /> ??
          </Button>
        </div>
        <div className="mt-4">
          <ResultPanel result={result} onPreviewImage={onPreviewImage} />
        </div>
      </div>
    </div>
  );
}

interface ImagePreviewModalProps {
  image: ImagePreviewState;
  onClose: () => void;
}

function ImagePreviewModal({ image, onClose }: ImagePreviewModalProps) {
  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  const altText = image.alt || '图片预览';

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div className="relative w-full max-w-4xl" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="absolute right-4 top-4 inline-flex items-center gap-2 rounded-full bg-white/80 px-4 py-2 text-sm font-medium text-foreground shadow ring-1 ring-border"
          onClick={onClose}
        >
          <X className="h-4 w-4" /> 关闭
        </button>
        <img src={image.src} alt={altText} className="max-h-[80vh] w-full rounded-3xl object-contain shadow-2xl" />
        {altText && <p className="mt-3 text-center text-sm text-white/80">{altText}</p>}
      </div>
    </div>
  );
}
