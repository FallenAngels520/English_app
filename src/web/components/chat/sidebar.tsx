'use client';

import { Conversation } from '@/types/chat';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Plus, MessageSquare, Trash2, BookOpen } from 'lucide-react';
import { ThemeToggle } from '@/components/theme-toggle';

interface SidebarProps {
  sessions: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onOpenLibrary: () => void;
  hasLibraryItems: boolean;
}

export function Sidebar({ sessions, activeId, onSelect, onCreate, onDelete, onOpenLibrary, hasLibraryItems }: SidebarProps) {
  return (
    <aside className="flex h-full w-72 flex-shrink-0 flex-col border-r border-border/80 bg-card/95 backdrop-blur">
      <div className="border-b px-4 py-3">
        <Button onClick={onCreate} className="w-full gap-2" variant="default">
          <Plus className="h-4 w-4" /> 新会话
        </Button>
      </div>
      <div className="border-b px-4 pb-3 pt-3">
        <Button
          onClick={onOpenLibrary}
          className="w-full gap-2"
          variant="secondary"
          disabled={!hasLibraryItems}
        >
          <BookOpen className="h-4 w-4" /> 卡片库
        </Button>
      </div>
      <div className="chat-scroll flex-1 overflow-y-auto p-3">
        {sessions.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border/70 bg-card/70 p-4 text-sm text-muted-foreground">
            还没有会话，点击「新会话」开始聊天。
          </p>
        ) : (
          <ul className="space-y-1.5">
            {sessions.map((session) => {
              const isActive = activeId === session.id;
              const title = session.title || '未命名会话';
              return (
                <li key={session.id}>
                  <div
                    className={cn(
                      'group flex items-center justify-between rounded-xl border px-3 py-2 text-sm transition-all',
                      isActive
                        ? 'border-primary/40 bg-primary/10 text-foreground shadow-sm'
                        : 'border-transparent text-muted-foreground hover:border-border/80 hover:bg-muted/40'
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                      onClick={() => onSelect(session.id)}
                      aria-current={isActive}
                      title={title}
                    >
                      <MessageSquare
                        className={cn('h-4 w-4 flex-shrink-0', isActive ? 'text-primary' : 'text-muted-foreground')}
                      />
                      <span className="truncate font-medium">{title}</span>
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={cn(
                        'text-muted-foreground transition group-hover:opacity-100 focus-visible:opacity-100',
                        isActive ? 'opacity-100' : 'opacity-0'
                      )}
                      onClick={() => onDelete(session.id)}
                      aria-label="删除会话"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="flex items-center justify-between border-t px-4 py-3 text-sm text-muted-foreground">
        <span>外观</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
