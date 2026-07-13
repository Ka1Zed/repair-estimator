import type { EstimateScope } from "../store/projectStore";

export interface ProjectRoom {
  name: string;
  room_type: string;
  height: number;
  points: { x: number; y: number }[];
  openings: { type: "door" | "window"; width: number; height: number }[];
  works: Record<string, unknown>;
}

export interface ProjectSummary {
  id: number;
  name: string;
  city: string;
  created_at: string;
  updated_at: string;
}

export interface Project extends ProjectSummary {
  rooms: ProjectRoom[];
  scope: EstimateScope;
  share_token: string;
}

export interface SharedProject {
  name: string;
  city: string;
  rooms: ProjectRoom[];
  scope: EstimateScope;
  created_at: string;
  updated_at: string;
}

export interface ProjectPayload {
  name: string;
  city: string;
  scope: EstimateScope;
  rooms: ProjectRoom[];
}
