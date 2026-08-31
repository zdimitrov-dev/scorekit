export type Source = "youtube" | "imslp" | "musescore";

export interface CardMeta {
  match_score?: number;
  rank?: number;
  composer?: string;
  view_count?: number;
  published_at?: string;
  duration_seconds?: number;
  is_compilation?: boolean;
  is_remix?: boolean;
  has_sheet_music_link?: boolean;
  sheet_music_links?: string[];
  instrumentation?: string;
  piece_style?: string;
  year?: string;
  is_public_domain?: boolean;
  licenses?: string[];
  parent_work?: string;
  resolved_from_disambiguation?: string;
  canonical_page?: string;
  [k: string]: unknown;
}

export interface Piece {
  id: string;
  title: string;
  composer: string | null;
}

export interface FeedCard {
  id: string;
  source: Source;
  kind: string | null;
  external_id: string;
  url: string;
  title: string | null;
  thumbnail_url: string | null;
  author: string | null;
  metadata: CardMeta;
  piece: Piece | null;
}
