export type UserProfile = {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string;
  isAdmin: boolean;
};

export type AccountListItem = {
  id: string;
  username: string;
  displayName: string;
  profileUrl: string;
  subscribed: boolean;
  backfillCompletedAt: string | null;
};

export type RequestListItem = {
  id: string;
  status: string;
  rawInput: string;
  normalizedUsername: string;
  createdAt: string;
};

export type FeedDay = {
  id: string;
  username: string;
  displayName: string;
  profileUrl: string;
  date: string;
  status: string;
  noteCount: number;
  summary: string;
  notes: Array<{ note_id: string; url: string; title: string; publish_time: string | null }>;
  viewpoints: Array<Record<string, unknown>>;
  updatedAt: string;
};

export type EntityListItem = {
  key: string;
  displayName: string;
  latestDate: string | null;
  mentionCount: number;
  authorCount: number;
};

export type AdminRequestItem = {
  id: string;
  rawInput: string;
  normalizedUsername: string;
  requesterEmail: string;
  createdAt: string;
  account: {
    id: string;
    username: string;
    displayName: string;
    profileUrl: string;
    status: string;
  };
};

export type AdminJobItem = {
  id: string;
  kind: string;
  status: string;
  summary: string;
  errorText: string | null;
  createdAt: string;
  finishedAt: string | null;
};
