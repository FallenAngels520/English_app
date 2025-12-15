'use client';

import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import tsx from 'react-syntax-highlighter/dist/cjs/languages/prism/tsx';
import javascript from 'react-syntax-highlighter/dist/cjs/languages/prism/javascript';
import python from 'react-syntax-highlighter/dist/cjs/languages/prism/python';
import bash from 'react-syntax-highlighter/dist/cjs/languages/prism/bash';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import { ResultPanel } from '@/components/chat/result-panel';
import type { ChatMessage as ChatMessageType } from '@/types/chat';
import type { WordMemoryResult } from '@/types/result';

SyntaxHighlighter.registerLanguage('tsx', tsx);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('bash', bash);

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
  result?: WordMemoryResult | null;
  onPreviewImage?: (src: string | null | undefined, alt?: string) => void;
}

export const ChatMessage = memo(function ChatMessage({ message, isStreaming, result, onPreviewImage }: ChatMessageProps) {
  const { theme } = useTheme();
  const isUser = message.role === 'user';
  const showCard =
    !isUser && !!result && result.intent !== 'small_talk' && result.intent !== 'out_of_scope';

  const bubbleClasses = isUser
    ? 'bg-primary text-primary-foreground ml-auto'
    : cn(
        'bg-muted text-foreground border border-border',
        message.error && 'border-destructive/60 text-destructive'
      );
  const normalizedContent = normalizeReplyText(message.content);
  const isThinking = !normalizedContent && isStreaming;
  const content = normalizedContent || '';

  return (
    <div className={cn('flex w-full gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-sm font-semibold text-primary">
          AI
        </div>
      )}
      {showCard ? (
        <div className="max-w-[min(720px,85%)]" aria-live={isStreaming ? 'polite' : 'off'}>
          <ResultPanel result={result} onPreviewImage={onPreviewImage} />
        </div>
      ) : (
        <div
          className={cn(
            'max-w-[min(720px,85%)] rounded-2xl px-4 py-3 text-sm shadow-sm transition-all',
            bubbleClasses
          )}
          aria-live={isStreaming ? 'polite' : 'off'}
        >
          {isThinking ? (
            <div className="flex items-center gap-3">
              <span>AI 正在思考</span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: '0ms' }} />
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: '150ms' }} />
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="markdown-body break-words text-[0.95rem]"
              components={{
                code({ node, inline, className, children, ...props }) {
                  const match = /language-(\w+)/.exec(className ?? '');
                  const language = match?.[1] ?? '';
                  if (inline || !language) {
                    return (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  }
                  return (
                    <SyntaxHighlighter
                      language={language}
                      style={theme === 'dark' ? oneDark : oneLight}
                      PreTag="div"
                      customStyle={{ marginTop: '0.5rem' }}
                      wrapLongLines
                      {...props}
                    >
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  );
                }
              }}
            >
              {content}
            </ReactMarkdown>
          )}
          {message.error && <p className="mt-2 text-xs text-destructive">生成失败，请重试</p>}
        </div>
      )}
      {isUser && (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
          我
        </div>
      )}
    </div>
);
});

function normalizeReplyText(value?: string) {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed.startsWith('{')) {
    return value;
  }
  try {
    const parsed = JSON.parse(trimmed) as { reply_text?: string };
    if (parsed && typeof parsed.reply_text === 'string') {
      return parsed.reply_text;
    }
  } catch {
    // ignore parse errors
  }
  return value;
}
