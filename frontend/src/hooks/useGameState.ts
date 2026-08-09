import { useReducer, type Dispatch } from 'react';

export interface PlayerInfo {
  seat_idx: number;
  name: string;
  stack: number;
  current_bet: number;
  is_active: boolean;
  is_all_in: boolean;
  is_human: boolean;
}

export interface SeatInfo {
  seat_idx: number;
  name: string;
  is_human: boolean;
  bot_level: number | null;
  stack: number;
  hands: number;
  wins: number;
  net_chips: number;
}

export interface TableConfigData {
  small_blind: number;
  big_blind: number;
  default_buyin: number;
  max_seats: number;
}

export interface GameStateData {
  phase: string;
  community_cards: string[];
  pot: number;
  current_bet: number;
  current_player_idx: number | null;
  players: PlayerInfo[];
  round_history: { seat: number; action: string; amount: number }[];
}

interface HandStartData {
  table_id: string;
  phase: string;
  dealer_idx: number;
  current_player_idx: number | null;
  current_bet: number;
  players: PlayerInfo[];
  small_blind: number;
  big_blind: number;
  pot: number;
}

interface ShowdownData {
  hands: Record<number, string>;
  awards: { seat_idx: number; amount: number; hand: string }[];
}

export type GameMsg =
  | { type: 'table_state'; table_id: string; seats: SeatInfo[]; phase: string;
      max_seats: number; config: TableConfigData }
  | { type: 'hand_start' } & HandStartData
  | { type: 'hole_cards'; cards: string[] }
  | { type: 'game_state_update' } & GameStateData
  | { type: 'hand_result' } & GameStateData & { showdown: ShowdownData }
  | { type: 'error'; message: string };

interface AppState {
  phase: string;
  players: PlayerInfo[];
  communityCards: string[];
  pot: number;
  currentBet: number;
  currentPlayerIdx: number | null;
  roundHistory: GameStateData['round_history'];
  holeCards: string[];
  showdown: ShowdownData | null;
  mySeat: number | null;
  tableId: string | null;
  maxSeats: number;
  connected: boolean;
  seats: SeatInfo[];
  config: TableConfigData | null;
}

type Action =
  | { type: 'SET_TABLE'; tableId: string }
  | { type: 'TABLE_STATE'; data: GameMsg & { type: 'table_state' } }
  | { type: 'HAND_START'; data: GameMsg & { type: 'hand_start' } }
  | { type: 'HOLE_CARDS'; cards: string[] }
  | { type: 'GAME_UPDATE'; data: GameMsg & { type: 'game_state_update' } }
  | { type: 'HAND_RESULT'; data: GameMsg & { type: 'hand_result' } }
  | { type: 'SET_MY_SEAT'; seat: number | null }
  | { type: 'SET_CONNECTED'; connected: boolean };

export const initialState: AppState = {
  phase: 'WAITING',
  players: [],
  communityCards: [],
  pot: 0,
  currentBet: 0,
  currentPlayerIdx: null,
  roundHistory: [],
  holeCards: [],
  showdown: null,
  mySeat: null,
  tableId: null,
  maxSeats: 9,
  connected: false,
  seats: [],
  config: null,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_TABLE':
      return { ...state, tableId: action.tableId };
    case 'TABLE_STATE':
      return {
        ...state,
        seats: action.data.seats,
        config: action.data.config,
        maxSeats: action.data.max_seats,
      };
    case 'HAND_START':
      return {
        ...state,
        phase: action.data.phase,
        players: action.data.players,
        pot: action.data.pot,
        communityCards: [],
        holeCards: [],
        showdown: null,
        roundHistory: [],
        currentBet: action.data.current_bet ?? 0,
        currentPlayerIdx: action.data.current_player_idx ?? null,
      };
    case 'HOLE_CARDS':
      return { ...state, holeCards: action.cards };
    case 'GAME_UPDATE':
      return {
        ...state,
        phase: action.data.phase,
        players: action.data.players,
        communityCards: action.data.community_cards,
        pot: action.data.pot,
        currentBet: action.data.current_bet,
        currentPlayerIdx: action.data.current_player_idx,
        roundHistory: action.data.round_history,
      };
    case 'HAND_RESULT':
      return {
        ...state,
        ...action.data,
        phase: action.data.phase,
        showdown: action.data.showdown,
      };
    case 'SET_MY_SEAT':
      return { ...state, mySeat: action.seat };
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected };
    default:
      return state;
  }
}

export function useGameState(): [AppState, Dispatch<Action>] {
  return useReducer(reducer, initialState);
}
