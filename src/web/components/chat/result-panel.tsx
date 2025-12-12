'use client';

import { Image as ImageIcon, Maximize2, Volume2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { WordMemoryResult } from '@/types/result';

interface ResultPanelProps {
  result: WordMemoryResult;
  onPreviewImage?: (src: string | null | undefined, alt?: string) => void;
}

export function ResultPanel({ result, onPreviewImage }: ResultPanelProps) {
  if (!result) return null;

  const wordBlock = result.word_block;
  const media = result.media;
  const status = result.status;
  const image = media?.image;
  const audio = media?.audio;
  const reason = status?.reason ?? '暂无生成理由';
  const meaning = wordBlock?.meaning;
  const homophone = wordBlock?.homophone;
  const phonetic = wordBlock?.phonetic;

  return (
    <section className="space-y-5 rounded-2xl border border-border bg-card/70 p-6 shadow-sm">
      {wordBlock && (
        <div className="flex flex-col gap-1 text-center">
          <h2 className="text-2xl font-semibold leading-tight">
            {wordBlock.word ?? '暂无词条'}
            {phonetic?.ipa && <span className="ml-3 text-base text-muted-foreground">{phonetic.ipa}</span>}
          </h2>
          {phonetic?.pronunciation_note && (
            <p className="text-xs text-muted-foreground">{phonetic.pronunciation_note}</p>
          )}
        </div>
      )}

      {wordBlock && (
        <div className="space-y-4 text-sm leading-relaxed text-foreground">
          {meaning && (
            <div className="space-y-1">
              <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">词义</h3>
              <p className="text-base font-medium">
                {meaning.pos && <span className="mr-2 text-muted-foreground">{meaning.pos}</span>}
                {meaning.cn}
              </p>
              {meaning.en && <p className="text-sm text-muted-foreground">{meaning.en}</p>}
            </div>
          )}
          {homophone && (homophone.text || homophone.explanation) && (
            <div className="space-y-1">
              <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">谐音梗</h3>
              {homophone.text && <p className="text-base">{homophone.text}</p>}
              {homophone.explanation && <p className="text-sm text-muted-foreground">{homophone.explanation}</p>}
            </div>
          )}
          {wordBlock.story && (
            <div className="space-y-1">
              <h3 className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">故事场景</h3>
              <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">{wordBlock.story}</p>
            </div>
          )}
        </div>
      )}

      {!wordBlock && <p className="text-sm text-muted-foreground">{reason}</p>}

      {(image || audio) && (
        <div className="space-y-6">
          {image && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <ImageIcon className="h-4 w-4" /> 配图
              </div>
              <div className="relative overflow-hidden rounded-2xl border border-border bg-background" style={{ aspectRatio: '4 / 3' }}>
                <img
                  src={image.url}
                  alt={wordBlock?.word ?? 'mnemonic image'}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
                {onPreviewImage && image.url && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="absolute right-3 top-3 h-8 gap-2 rounded-full bg-background/85 text-xs shadow ring-1 ring-border backdrop-blur"
                    onClick={() => onPreviewImage(image.url, wordBlock?.word)}
                  >
                    <Maximize2 className="h-3.5 w-3.5" /> 放大查看
                  </Button>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                风格：{image.style || '默认'} · 情绪：{image.mood || '默认'}
              </p>
            </div>
          )}
          {audio && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <Volume2 className="h-4 w-4" /> 配音
              </div>
              <audio controls src={audio.url} className="w-full" preload="metadata" />
              <p className="text-xs text-muted-foreground">
                声线：{audio.voice_profile_id || '默认'}
                {typeof audio.duration_sec === 'number' && audio.duration_sec > 0 && ` · 时长 ${audio.duration_sec.toFixed(1)}s`}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="rounded-2xl bg-muted/30 p-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">生成理由</p>
        <p className="mt-1 leading-relaxed">{reason}</p>
      </div>
    </section>
  );
}
