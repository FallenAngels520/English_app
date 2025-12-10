export interface Phonetic {
  ipa?: string | null;
  pronunciation_note?: string | null;
}

export interface Homophone {
  text: string;
  raw?: string | null;
  explanation?: string | null;
}

export interface Meaning {
  pos?: string | null;
  cn: string;
  en?: string | null;
}

export interface WordBlock {
  word: string;
  phonetic?: Phonetic | null;
  homophone: Homophone;
  story: string;
  meaning: Meaning;
}

export interface ImageMedia {
  url: string;
  style?: string | null;
  mood?: string | null;
  updated_at?: string | null;
}

export interface AudioMedia {
  url: string;
  voice_profile_id?: string | null;
  duration_sec?: number | null;
  updated_at?: string | null;
}

export interface MediaBlock {
  image?: ImageMedia | null;
  audio?: AudioMedia | null;
}

export interface MnemonicStyle {
  humor?: 'none' | 'light' | 'dark' | 'aggressive';
  dialect?: 'none' | 'mandarin' | 'dongbei' | 'cantonese';
  complexity?: 'simple' | 'normal' | 'complex';
  extra_tags?: string[];
}

export interface ImageStyle {
  need_image?: boolean;
  style?: 'none' | 'cute' | 'comic' | 'realistic' | 'anime';
  mood?: 'neutral' | 'funny' | 'dark' | 'warm';
  extra_tags?: string[];
}

export interface VoiceStyle {
  preset_id?: string | null;
  gender?: 'male' | 'female' | 'neutral';
  energy?: 'low' | 'medium' | 'high';
  pitch?: 'low' | 'medium' | 'high';
  speed?: 'slow' | 'normal' | 'fast';
  tone?: 'soft' | 'normal' | 'bright';
}

export interface StylesBlock {
  style_profile_id?: 'simple_clean' | 'funny' | 'aggressive' | 'dongbei_funny' | 'other' | null;
  mnemonic_style?: MnemonicStyle | null;
  image_style?: ImageStyle | null;
  voice_style?: VoiceStyle | null;
}

export interface StatusBlock {
  is_first_time: boolean;
  intent:
    | 'new_word'
    | 'refine_mnemonic'
    | 'change_image'
    | 'change_audio'
    | 'update_preferences'
    | 'explain'
    | 'small_talk'
    | 'out_of_scope';
  updated_parts: Array<'mnemonic' | 'image' | 'audio'>;
  scope: 'this_turn' | 'session_default';
  reason: string;
}

export interface WordMemoryResult {
  type: 'word_memory';
  intent:
    | 'new_word'
    | 'refine_mnemonic'
    | 'change_image'
    | 'change_audio'
    | 'update_preferences'
    | 'explain'
    | 'small_talk'
    | 'out_of_scope';
  word_block: WordBlock | null;
  media: MediaBlock | null;
  styles: StylesBlock | null;
  status: StatusBlock;
}
