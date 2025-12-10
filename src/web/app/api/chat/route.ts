import { NextResponse } from 'next/server';

interface OutgoingMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

const DEFAULT_BACKEND_URL = process.env.AGENT_API_BASE_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: Request) {
  const { messages = [], sessionId, configurable } = await request.json();

  if (!Array.isArray(messages) || messages.length === 0) {
    return NextResponse.json({ error: 'messages is required' }, { status: 400 });
  }

  const payload = {
    session_id: typeof sessionId === 'string' && sessionId.trim().length > 0 ? sessionId : 'default',
    configurable: typeof configurable === 'object' && configurable != null ? configurable : undefined,
    messages: (messages as OutgoingMessage[]).map((message) => ({
      role: message.role,
      content: message.content ?? ''
    }))
  };

  let backendResponse: Response;
  try {
    backendResponse = await fetch(`${DEFAULT_BACKEND_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  } catch (networkError) {
    return NextResponse.json(
      { error: `无法连接到后台服务: ${(networkError as Error).message}` },
      { status: 502 }
    );
  }

  const text = await backendResponse.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }

  if (!backendResponse.ok) {
    const detail = (data as { detail?: string })?.detail ?? 'Backend error';
    return NextResponse.json({ error: detail }, { status: backendResponse.status });
  }

  return NextResponse.json(data);
}
