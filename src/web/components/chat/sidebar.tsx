'use client';

import { Conversation } from '@/types/chat';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Plus, MessageSquare, Trash2 } from 'lucide-react';
import { ThemeToggle } from '@/components/theme-toggle';

interface SidebarProps {
  sessions: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}

export function Sidebar({ sessions, activeId, onSelect, onCreate, onDelete }: SidebarProps) {
  return (
    <aside className="flex h-full w-64 flex-shrink-0 flex-col border-r bg-card">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <Button onClick={onCreate} className="w-full gap-2" variant="default">
          <Plus className="h-4 w-4" /> 新会话
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 chat-scroll">
        {sessions.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">还没有会话，点击“新会话”开始聊天。</p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <div
                  className={cn(
                    'group flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition hover:bg-accent',
                    activeId === session.id ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'
                  )}
                >
                  <button
                    type="button"
                    className="flex flex-1 items-center gap-2 text-left"
                    onClick={() => onSelect(session.id)}
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span className="line-clamp-1">{session.title || '未命名会话'}</span>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="invisible text-muted-foreground hover:text-destructive group-hover:visible"
                    onClick={() => onDelete(session.id)}
                    aria-label="删除会话"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
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
