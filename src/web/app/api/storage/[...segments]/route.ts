import { NextResponse } from 'next/server';

const DEFAULT_BACKEND_URL = process.env.AGENT_API_BASE_URL ?? 'http://127.0.0.1:8000';

function buildBackendUrl(segments: string[] | undefined, search: string) {
  const normalizedSegments = segments && segments.length > 0 ? `/${segments.join('/')}` : '';
  return `${DEFAULT_BACKEND_URL.replace(/\/$/, '')}/storage${normalizedSegments}${search}`;
}

async function forwardRequest(url: string) {
  let backendResponse: Response;
  try {
    backendResponse = await fetch(url);
  } catch (networkError) {
    return NextResponse.json(
      { error: `无法连接到后端服务: ${(networkError as Error).message}` },
      { status: 502 }
    );
  }

  const payloadText = await backendResponse.text();
  const asJson = payloadText ? safeJsonParse(payloadText) : null;

  if (!backendResponse.ok) {
    const detail =
      (asJson as { detail?: string; error?: string } | null)?.detail ??
      (asJson as { error?: string } | null)?.error ??
      payloadText ||
      'Backend error';
    return NextResponse.json({ error: detail }, { status: backendResponse.status });
  }

  return NextResponse.json(asJson);
}

function safeJsonParse(text: string) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function GET(request: Request, context: { params: { segments?: string[] } }) {
  const url = new URL(request.url);
  const backendUrl = buildBackendUrl(context.params.segments, url.search);
  return forwardRequest(backendUrl);
}
