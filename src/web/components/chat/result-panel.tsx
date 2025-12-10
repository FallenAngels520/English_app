'use client';

import { Image as ImageIcon, Volume2 } from 'lucide-react';
import type { WordMemoryResult } from '@/types/result';

interface ResultPanelProps {
  result: WordMemoryResult;
}

export function ResultPanel({ result }: ResultPanelProps) {
  if (!result) return null;

  const wordBlock = result.word_block;
  const media = result.media;
  const status = result.status;
  const image = media?.image;
  const audio = media?.audio;

  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card/60 p-6 shadow-sm">
      {wordBlock && (
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-semibold text-center">
            {wordBlock.word ?? '暂无词条'}
            {wordBlock.phonetic?.ipa && <span className="ml-3 text-base text-muted-foreground">{wordBlock.phonetic.ipa}</span>}
          </h2>
          {wordBlock.phonetic?.pronunciation_note && (
            <p className="text-xs text-muted-foreground text-center">{wordBlock.phonetic.pronunciation_note}</p>
          )}
        </div>
      )}

      {wordBlock && (
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground">词义</h3>
            <p className="text-base font-medium">
              {wordBlock.meaning.pos && <span className="mr-2 text-muted-foreground">{wordBlock.meaning.pos}</span>}
              {wordBlock.meaning.cn}
            </p>
            {wordBlock.meaning.en && <p className="text-sm text-muted-foreground">{wordBlock.meaning.en}</p>}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground">谐音梗</h3>
            <p className="text-base">{wordBlock.homophone.text}</p>
            {wordBlock.homophone.explanation && (
              <p className="text-sm text-muted-foreground">{wordBlock.homophone.explanation}</p>
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground">故事场景</h3>
            <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">{wordBlock.story}</p>
          </div>
        </div>
      )}

      {!wordBlock && <p className="text-sm text-muted-foreground">{status.reason}</p>}

      {(image || audio) && (
        <div className="space-y-4">
          {image && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <ImageIcon className="h-4 w-4" /> 配图
              </div>
              <div className="overflow-hidden rounded-xl border border-border bg-background">
                <img
                  src={image.url}
                  alt={wordBlock?.word ?? 'mnemonic image'}
                  className="w-full h-auto"
                  loading="lazy"
                />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                风格：{image.style || '默认'} · 情绪：{image.mood || '默认'}
              </p>
            </div>
          )}
          {audio && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <Volume2 className="h-4 w-4" /> 配音
              </div>
              <audio controls src={audio.url} className="w-full" preload="metadata" />
              <p className="mt-2 text-xs text-muted-foreground">
                声线：{audio.voice_profile_id || '默认'}
                {typeof audio.duration_sec === 'number' && audio.duration_sec > 0 && ` · 时长 ${audio.duration_sec.toFixed(1)}s`}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="rounded-lg bg-muted/40 p-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">生成理由</p>
        <p>{status.reason}</p>
      </div>
    </section>
  );
}
