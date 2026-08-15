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
  connected: boolean;
  is_owner: boolean;
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
  min_raise: number;
  current_player_idx: number | null;
  players: PlayerInfo[];
  round_history: { seat: number; action: string; amount: number }[];
  dealer_idx: number | null;
  sb_seat: number | null;
  bb_seat: number | null;
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
  min_raise: number;
  pot: number;
  sb_seat: number | null;
  bb_seat: number | null;
}

interface ShowdownData {
  hands: Record<number, string>;
  awards: { seat_idx: number; amount: number; hand: string }[];
  // Seats that reached showdown → their hole cards, revealed by the server
  // so the frontend can flip the seat backs face-up.
  hole_cards?: Record<number, string[]>;
}

export type GameMsg =
  | { type: 'table_state'; table_id: string; seats: SeatInfo[]; phase: string;
      max_seats: number; config: TableConfigData }
  | { type: 'hand_start' } & HandStartData
  | { type: 'hole_cards'; cards: string[] }
  | { type: 'game_state_update' } & GameStateData
  | { type: 'hand_result' } & GameStateData & { showdown: ShowdownData }
  | { type: 'reclaim_token'; token: string; seat: number }
  | { type: 'room_closed'; table_id: string }
  | { type: 'kicked'; message?: string }
  | { type: 'error'; message: string };

interface AppState {
  phase: string;
  players: PlayerInfo[];
  communityCards: string[];
  pot: number;
  currentBet: number;
  minRaise: number;
  currentPlayerIdx: number | null;
  roundHistory: GameStateData['round_history'];
  holeCards: string[];
  showdown: ShowdownData | null;
  mySeat: number | null;
  tableId: string | null;
  maxSeats: number;
  connected: boolean;
  turnEpoch: number;
  seats: SeatInfo[];
  config: TableConfigData | null;
  dealerIdx: number | null;
  sbSeat: number | null;
  bbSeat: number | null;
}

type Action =
  | { type: 'SET_TABLE'; tableId: string }
  | { type: 'TABLE_STATE'; data: GameMsg & { type: 'table_state' } }
  | { type: 'HAND_START'; data: GameMsg & { type: 'hand_start' } }
  | { type: 'HOLE_CARDS'; cards: string[] }
  | { type: 'GAME_UPDATE'; data: GameMsg & { type: 'game_state_update' } }
  | { type: 'HAND_RESULT'; data: GameMsg & { type: 'hand_result' } }
  | { type: 'SET_MY_SEAT'; seat: number | null }
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'BUMP_TURN_EPOCH' };

export const initialState: AppState = {
  phase: 'WAITING',
  players: [],
  communityCards: [],
  pot: 0,
  currentBet: 0,
  minRaise: 0,
  currentPlayerIdx: null,
  roundHistory: [],
  holeCards: [],
  showdown: null,
  mySeat: null,
  tableId: null,
  maxSeats: 9,
  connected: false,
  turnEpoch: 0,
  seats: [],
  config: null,
  dealerIdx: null,
  sbSeat: null,
  bbSeat: null,
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
        minRaise: action.data.min_raise ?? 0,
        currentPlayerIdx: action.data.current_player_idx ?? null,
        dealerIdx: action.data.dealer_idx ?? null,
        sbSeat: action.data.sb_seat ?? null,
        bbSeat: action.data.bb_seat ?? null,
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
        minRaise: action.data.min_raise ?? 0,
        currentPlayerIdx: action.data.current_player_idx,
        roundHistory: action.data.round_history,
        dealerIdx: action.data.dealer_idx ?? null,
        sbSeat: action.data.sb_seat ?? null,
        bbSeat: action.data.bb_seat ?? null,
      };
    case 'HAND_RESULT':
      return {
        ...state,
        ...action.data,
        phase: action.data.phase,
        minRaise: action.data.min_raise ?? 0,
        showdown: action.data.showdown,
      };
    case 'SET_MY_SEAT':
      return { ...state, mySeat: action.seat };
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected };
    case 'BUMP_TURN_EPOCH':
      // Server re-armed the action countdown (reclaim mid-turn) — the
      // ActionBar restarts its local clock when this changes.
      return { ...state, turnEpoch: state.turnEpoch + 1 };
    default:
      return state;
  }
}

export function useGameState(): [AppState, Dispatch<Action>] {
  return useReducer(reducer, initialState);
}
