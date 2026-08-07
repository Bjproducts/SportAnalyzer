export type Venue = "home" | "away" | "all";
export type DataQualityStatus =
  | "complete"
  | "partial"
  | "missing_sot"
  | "missing_lineup"
  | "provider_error"
  | "manually_verified";

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  uptime_seconds: number;
  database: "ok" | "unavailable";
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface Team {
  id: number;
  name: string;
  short_name: string | null;
  country: string | null;
  logo_url: string | null;
}

export interface Player {
  id: number;
  display_name: string;
  full_name: string;
  common_name: string | null;
  nationality: string | null;
  primary_position: string | null;
  position_group: string;
  photo_url: string | null;
  current_team: Team | null;
}

export interface PlayerSearchResponse {
  items: Player[];
  pagination: Pagination;
}

export interface TeamsResponse {
  items: Team[];
  pagination: Pagination;
}

export interface TeamPlayersResponse {
  team: Team;
  items: Player[];
}

export interface RateResult {
  successes: number;
  valid: number;
  failures: number;
  missing: number;
  percentage: number | null;
  criterion: string;
  description: string;
}

export interface PlayerMatch {
  fixture_id: number;
  fixture_date: string;
  competition: { id: number; name: string };
  season: { id: number; label: string };
  team: Team;
  opponent: Team;
  venue: "home" | "away";
  started: boolean;
  substitute_appearance: boolean;
  minutes_played: number | null;
  position: string | null;
  shots: number | null;
  shots_on_target: number | null;
  goals: number | null;
  assists: number | null;
  team_shots: number | null;
  team_shots_on_target: number | null;
  player_share_of_team_sot: number | null;
  one_plus_sot: boolean | null;
  two_plus_sot: boolean | null;
  early_exit: boolean | null;
  data_quality_status: DataQualityStatus;
}

export interface PlayerMatchesResponse {
  player: Player;
  items: PlayerMatch[];
  pagination: Pagination;
}

export interface SotSummary {
  total_appearances: number;
  total_starts: number;
  substitute_appearances: number;
  threshold_rates: Record<string, RateResult>;
  total_shots: number;
  total_shots_on_target: number;
  starts_missing_sot: number;
  average_shots_per_start: number | null;
  average_sot_per_start: number | null;
  shots_per_90: number | null;
  sot_per_90: number | null;
  shot_accuracy: number | null;
  team_sot_share: number | null;
  minutes: {
    starts_considered: number;
    starts_with_known_minutes: number;
    pct_at_least_60: number | null;
    pct_at_least_80: number | null;
    early_exits: number;
    average_minutes_per_start: number | null;
    total_minutes: number;
  } | null;
}

export interface PlayerSummaryResponse {
  player: Player;
  summary: SotSummary;
  recent_form: Record<string, { window: number; starts_available: number; rate: RateResult }>;
}

export interface SplitEntry {
  key: string | number;
  label: string;
  rate: RateResult;
  average_sot: number | null;
  average_shots: number | null;
  total_starts: number;
}

export interface PlayerSplitsResponse {
  player: Player;
  threshold: number;
  venue: { home: RateResult; away: RateResult; overall: RateResult };
  competitions: SplitEntry[];
  seasons: SplitEntry[];
  opponents: SplitEntry[];
}

export interface PlayerStreaksResponse {
  player: Player;
  streak: {
    threshold: number;
    current: number;
    longest: number;
    missing_in_window: number;
    reliable: boolean;
    last_failure_date: string | null;
    last_failure_fixture_id: number | null;
    starts_since_last_failure: number;
    never_failed: boolean;
  };
}

export interface RankingEntry {
  rank: number;
  eligible: boolean;
  player: Player;
  rate: RateResult;
  last_five_rate: number | null;
  average_sot: number | null;
  average_minutes: number | null;
  current_streak: number;
  sample_adjusted_rate: number | null;
}

export interface TeamRankingsResponse {
  team: Team;
  venue: Venue;
  threshold: number;
  minimum_starts: number;
  last_n: 5 | 10 | 20;
  limit: number;
  items: RankingEntry[];
}

export interface ComparisonEntry {
  player: Player;
  one_plus_rate: RateResult;
  two_plus_rate: RateResult;
  average_sot: number | null;
  sot_per_90: number | null;
  home_rate: RateResult;
  away_rate: RateResult;
  last_five_rate: RateResult;
  last_ten_rate: RateResult;
  current_streak: number;
  valid_starts: number;
}

export interface ComparisonResponse {
  items: ComparisonEntry[];
}

export type PreviewScoreLabel = "strong" | "viable" | "speculative";
export type PreviewConfidence = "high" | "medium" | "low";
export type DefenseLabel = "strong" | "neutral" | "vulnerable" | "unknown";

export interface Fixture {
  id: number;
  fixture_date: string;
  status: string;
  home_score: number | null;
  away_score: number | null;
  venue: string | null;
  round: string | null;
  competition: { id: number; name: string };
  season: { id: number; label: string };
  home_team: Team;
  away_team: Team;
}

export interface DefensiveContext {
  team: Team;
  average_sot_allowed: number | null;
  matches: number;
  label: DefenseLabel;
  description: string;
}

export interface FixtureCandidate {
  rank: number;
  research_score: number;
  score_label: PreviewScoreLabel;
  confidence: PreviewConfidence;
  player: Player;
  recent_rate: RateResult;
  venue_rate: RateResult;
  average_sot: number | null;
  average_minutes: number | null;
  reasons: string[];
  risks: string[];
}

export interface TeamFixturePreview {
  team: Team;
  opponent: Team;
  venue: "home" | "away";
  opponent_defense: DefensiveContext;
  candidates: FixtureCandidate[];
  warning: string | null;
}

export interface FixturePreview {
  fixture: Fixture;
  home: TeamFixturePreview;
  away: TeamFixturePreview;
}

export interface DailyFixtureAnalysisResponse {
  date: string;
  timezone: "UTC";
  generated_at: string;
  window: 5 | 10 | 20;
  fixtures: FixturePreview[];
  methodology: string;
  disclaimer: string;
}
