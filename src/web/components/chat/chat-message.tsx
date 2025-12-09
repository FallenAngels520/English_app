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
import type { ChatMessage as ChatMessageType } from '@/types/chat';

SyntaxHighlighter.registerLanguage('tsx', tsx);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('bash', bash);

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

export const ChatMessage = memo(function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const { theme } = useTheme();
  const isUser = message.role === 'user';
  const bubbleClasses = isUser
    ? 'bg-primary text-primary-foreground ml-auto'
    : cn('bg-muted text-foreground border border-border', message.error && 'border-destructive/60 text-destructive');

  return (
    <div className={cn('flex w-full gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20 text-sm font-semibold text-primary">
          AI
        </div>
      )}
      <div className={cn('max-w-[75%] rounded-2xl px-4 py-3 text-sm shadow-sm', bubbleClasses)}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          className="markdown-body"
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
          {message.content || (isStreaming ? 'AI 正在思考…' : '')}
        </ReactMarkdown>
        {message.error && <p className="mt-2 text-xs text-destructive">生成失败，请重试</p>}
      </div>
      {isUser && (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
          我
        </div>
      )}
    </div>
  );
});
