'use client';

import * as React from 'react';
import { Loader2, Send } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

interface ChatInputProps {
  value: string;
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function ChatInput({ value, placeholder, disabled, isLoading, onChange, onSubmit }: ChatInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!disabled) {
        onSubmit();
      }
    }
  };

  React.useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [value]);

  const isSubmitDisabled = disabled || !value.trim();

  return (
    <div className="flex gap-2 rounded-xl border border-border bg-card/80 p-3 shadow-sm">
      <Textarea
        ref={textareaRef}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        rows={1}
        onKeyDown={handleKeyDown}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-[48px] max-h-48 resize-none border-none bg-transparent text-sm leading-6 focus-visible:ring-0"
        aria-label="聊天输入框"
      />
      <Button
        type="button"
        onClick={onSubmit}
        disabled={isSubmitDisabled}
        className="self-end min-w-[44px]"
        aria-label="发送消息"
      >
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
      </Button>
    </div>
  );
}
