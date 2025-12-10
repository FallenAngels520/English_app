import type { WordMemoryResult } from './result';

export type ChatRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  error?: boolean;
}

export interface ConversationResult {
  id: string;
  result: WordMemoryResult;
  createdAt?: string | null;
  recordId?: string;
}

export interface CachedResponseRecord {
  session_id: string;
  record_id?: string;
  cached_at?: string | null;
  request: Record<string, unknown>;
  response: {
    reply_text?: string;
    final_output?: WordMemoryResult | null;
  };
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  finalOutputs: ConversationResult[];
}
