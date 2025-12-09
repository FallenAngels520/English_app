'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCcw, RotateCcw, StopCircle } from 'lucide-react';
import { Sidebar } from '@/components/chat/sidebar';
import { ChatInput } from '@/components/chat/chat-input';
import { ChatMessage } from '@/components/chat/chat-message';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type { ChatMessage as ChatMessageType, Conversation } from '@/types/chat';

const STORAGE_KEY = 'english-app-chat-sessions';
const ACTIVE_KEY = 'english-app-chat-active';

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
    title: '新会话',
    createdAt: now,
    updatedAt: now,
    messages: []
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
  if (!firstUser) return '新会话';
  const normalized = firstUser.content.replace(/\s+/g, ' ').trim();
  return normalized.length > 24 ? `${normalized.slice(0, 24)}…` : normalized || '新会话';
};

type MessagesUpdater = ChatMessageType[] | ((messages: ChatMessageType[]) => ChatMessageType[]);

export default function ChatPage() {
  const [sessions, setSessions] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [initialized, setInitialized] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const chatContainerRef = useRef<HTMLDivElement | null>(null);

  const activeSession = useMemo(() => sessions.find((session) => session.id === activeId) ?? null, [sessions, activeId]);

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
    const activeIdFromStorage = sessionsToUse.find((session) => session.id === storedActive)?.id ?? sessionsToUse[0].id;
    setSessions(sessionsToUse);
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
    const container = chatContainerRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [activeSession?.messages.length, isStreaming]);

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
          title: session.messages.length === 0 || session.title === '新会话' ? buildTitleFromMessages(nextMessages) : session.title,
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
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: messagesPayload.map(({ role, content }) => ({ role, content })) }),
          signal: controller.signal
        });

        if (!response.ok) {
          throw new Error('无法生成回复');
        }

        if (!response.body) {
          throw new Error('当前浏览器不支持流式响应');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          updateSessionMessages(sessionId, (messages) =>
            messages.map((message) =>
              message.id === assistantMessageId
                ? { ...message, content: `${message.content}${chunk}`, error: false }
                : message
            )
          );
        }
        setPendingUserMessage(null);
      } catch (chatError) {
        if ((chatError as DOMException).name === 'AbortError') {
          setError('生成已停止');
        } else {
          console.error(chatError);
          setError('生成失败，请重试');
          updateSessionMessages(sessionId, (messages) =>
            messages.map((message) => (message.id === assistantMessageId ? { ...message, error: true } : message))
          );
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
        setStreamingMessageId(null);
      }
    },
    [updateSessionMessages]
  );

  const sendNewMessage = useCallback(
    async (rawInput?: string) => {
      const session = ensureSession();
      const sessionId = session.id;
      const text = (rawInput ?? input).trim();
      if (!text) return;

      const userMessage = createMessage('user', text);
      const assistantMessage = createMessage('assistant', '');
      const nextMessages = [...session.messages, userMessage, assistantMessage];
      setPendingUserMessage(text);
      setStreamingMessageId(assistantMessage.id);
      setInput('');
      updateSessionMessages(sessionId, nextMessages);
      await runChat([...session.messages, userMessage], sessionId, assistantMessage.id);
    },
    [ensureSession, input, runChat, updateSessionMessages]
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
    await runChat(payload, activeSession.id, assistantMessage.id);
  }, [activeSession, runChat, updateSessionMessages]);

  const handleStop = () => {
    if (!abortControllerRef.current) return;
    abortControllerRef.current.abort();
  };

  const handleDeleteSession = (sessionId: string) => {
    setError(null);
    setPendingUserMessage(null);
    setStreamingMessageId(null);
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
  };

  const lastUserMessage = useMemo(() => {
    if (!activeSession) return null;
    return [...activeSession.messages].reverse().find((message) => message.role === 'user') ?? null;
  }, [activeSession]);

  if (!initialized) {
    return (
      <main className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
          <p>加载中…</p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-screen bg-background text-foreground">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onCreate={handleCreateSession}
        onDelete={handleDeleteSession}
      />
      <section className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h1 className="text-lg font-semibold">English 助手</h1>
            <p className="text-sm text-muted-foreground">支持 Markdown、代码高亮与流式回复</p>
          </div>
          <div className="flex gap-2">
            {isStreaming ? (
              <Button variant="destructive" onClick={handleStop} size="sm" className="gap-2">
                <StopCircle className="h-4 w-4" /> 停止生成
              </Button>
            ) : (
              <Button variant="secondary" onClick={replayLastUserMessage} size="sm" disabled={!lastUserMessage} className="gap-2">
                <RotateCcw className="h-4 w-4" /> 重新生成
              </Button>
            )}
          </div>
        </header>
        <div ref={chatContainerRef} className="chat-scroll flex-1 overflow-y-auto px-6 py-6">
          {!activeSession || activeSession.messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <RefreshCcw className="mb-4 h-10 w-10" />
              <p className="text-lg font-semibold">开始新的对话</p>
              <p className="text-sm">输入你的问题，按 Enter 即可发送。Shift+Enter 用于换行。</p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {activeSession.messages.map((message) => (
                <ChatMessage key={message.id} message={message} isStreaming={streamingMessageId === message.id && isStreaming} />
              ))}
            </div>
          )}
        </div>
        {error && (
          <div className="border-t bg-destructive/10 px-6 py-4">
            <Alert variant="destructive" className="bg-transparent">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>出错了</AlertTitle>
              <AlertDescription className="flex flex-wrap items-center gap-3">
                <span>{error}</span>
                <Button size="sm" variant="outline" onClick={replayLastUserMessage} className="gap-2">
                  <RefreshCcw className="h-4 w-4" /> 重试
                </Button>
              </AlertDescription>
            </Alert>
          </div>
        )}
        <div className="border-t bg-card/70 px-6 py-4">
          <ChatInput
            value={input}
            onChange={setInput}
            placeholder="和 English 助手聊天..."
            disabled={isStreaming}
            onSubmit={() => sendNewMessage()}
          />
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>Enter 发送 · Shift+Enter 换行</span>
            {pendingUserMessage && !isStreaming && (
              <Button variant="link" size="sm" onClick={replayLastUserMessage} className="p-0 text-xs">
                再试一次
              </Button>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
