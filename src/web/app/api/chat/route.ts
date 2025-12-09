import { NextResponse } from 'next/server';

interface IncomingMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export async function POST(request: Request) {
  const { messages = [] } = await request.json();
  const lastUserMessage = [...messages].reverse().find((message: IncomingMessage) => message.role === 'user');

  const prompt = lastUserMessage?.content ?? 'No question provided.';
  const suggestion = `这里有一个学习建议：尝试把“${prompt.slice(0, 40)}”扩展成至少三个例句。`;
  const mockReply = `你刚刚说的是：\n\n${prompt}\n\n${suggestion}\n\n**知识点**\n\n1. 识别关键信息并用自己的话改写。\n2. 把抽象概念拆解成简单的步骤。\n3. 如果需要代码，先写伪代码再实现。`;

  const encoder = new TextEncoder();
  const signal = request.signal;

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const chunks = mockReply.split(/(\s+)/).filter(Boolean);
      const abortHandler = () => {
        controller.close();
      };
      signal.addEventListener('abort', abortHandler);
      try {
        for (const chunk of chunks) {
          if (signal.aborted) break;
          controller.enqueue(encoder.encode(chunk));
          await new Promise((resolve) => setTimeout(resolve, 80));
        }
      } finally {
        signal.removeEventListener('abort', abortHandler);
        controller.close();
      }
    }
  });

  return new NextResponse(stream, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8'
    }
  });
}
