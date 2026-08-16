export interface RecentHand {
  table_id: string;
  board: string[];
  won: boolean;
  net: number | null;
  small_blind: number | null;
  big_blind: number | null;
  created_at: string;
}

export interface BlindsGroup {
  small_blind: number | null;
  big_blind: number | null;
  hands: number;
  wins: number;
  net_chips: number;
}

export interface ProfileAccount {
  username: string;
  hands: number;
  wins: number;
  net_chips: number;
  total_buyin: number;
  vpip_rate: number | null;
  pfr_rate: number | null;
  wtsd: number | null;
  last_active: string | null;
  recent_hands: RecentHand[];
  by_blinds: BlindsGroup[];
}

export interface ProfileData {
  name: string;
  is_human: boolean;
  bot_level: number | null;
  // Table context — absent for the lobby's own-profile view.
  stack?: number;
  buyin?: number;
  buyin_count?: number;
  hands: number;
  wins: number;
  net_chips: number;
  // Table-local poker tracking (null before the first observed hand).
  vpip?: number | null;
  pfr?: number | null;
  account: ProfileAccount | null;
}

interface Props {
  title: string;
  profile: ProfileData;
  onClose: () => void;
}

function WinPct({ wins, hands }: { wins: number; hands: number }) {
  return <>{hands > 0 ? Math.round((wins / hands) * 100) : 0}%</>;
}

function Chips({ value }: { value: number }) {
  return (
    <b className={value >= 0 ? 'lb-pos' : 'lb-neg'}>
      {value >= 0 ? '+' : ''}{value}
    </b>
  );
}

function Pct({ value }: { value: number | null | undefined }) {
  return <>{value == null ? '—' : `${Math.round(value * 100)}%`}</>;
}

function ShortDate({ iso }: { iso: string }) {
  return <>{iso.slice(0, 16).replace('T', ' ')}</>;
}

export default function ProfileDialog({ title, profile, onClose }: Props) {
  return (
    <div className="profile-overlay" onClick={onClose}>
      <div className="profile-dialog" onClick={e => e.stopPropagation()}>
        <div className="profile-head">
          <span className="profile-title">{title}</span>
          <button className="profile-close" onClick={onClose}>✕</button>
        </div>
        <div className="profile-row">
          <span>Name</span>
          <b>{profile.name}{!profile.is_human && ` (Bot L${profile.bot_level ?? 2})`}</b>
        </div>
        {profile.stack !== undefined && (
          <>
            <div className="profile-row"><span>Current stack</span><b>{profile.stack}</b></div>
            <div className="profile-row"><span>Total buy-in</span>
              <b>{profile.buyin ?? 0}{profile.buyin_count && profile.buyin_count > 1
                  ? ` (${profile.buyin_count}×)` : ''}</b></div>
            {profile.vpip != null && (
              <>
                <div className="profile-row"><span>VPIP (this table)</span><b><Pct value={profile.vpip} /></b></div>
                <div className="profile-row"><span>PFR (this table)</span><b><Pct value={profile.pfr} /></b></div>
              </>
            )}
          </>
        )}
        <div className="profile-row"><span>Hands (this table)</span><b>{profile.hands}</b></div>
        <div className="profile-row"><span>Wins (this table)</span><b>{profile.wins}</b></div>
        <div className="profile-row"><span>Win rate</span><b><WinPct wins={profile.wins} hands={profile.hands} /></b></div>
        <div className="profile-row"><span>Net (this table)</span><Chips value={profile.net_chips} /></div>

        {profile.account ? (
          <>
            <div className="profile-divider" />
            <div className="profile-subtitle">Lifetime · {profile.account.username}</div>
            <div className="profile-row"><span>Hands</span><b>{profile.account.hands}</b></div>
            <div className="profile-row"><span>Wins</span><b>{profile.account.wins}</b></div>
            <div className="profile-row"><span>Win rate</span><b><WinPct wins={profile.account.wins} hands={profile.account.hands} /></b></div>
            <div className="profile-row"><span>Net chips</span><Chips value={profile.account.net_chips} /></div>
            <div className="profile-row"><span>VPIP</span><b><Pct value={profile.account.vpip_rate} /></b></div>
            <div className="profile-row"><span>PFR</span><b><Pct value={profile.account.pfr_rate} /></b></div>
            <div className="profile-row"><span>W$SD</span><b><Pct value={profile.account.wtsd} /></b></div>
            <div className="profile-row"><span>Total buy-in</span><b>{profile.account.total_buyin}</b></div>
            {profile.account.total_buyin > 0 && (
              <div className="profile-row"><span>ROI</span>
                <Chips value={Math.round(
                  (profile.account.net_chips / profile.account.total_buyin) * 100)} /></div>
            )}
            {profile.account.last_active && (
              <div className="profile-row"><span>Last active</span>
                <b><ShortDate iso={profile.account.last_active} /></b></div>
            )}

            {profile.account.by_blinds.length > 0 && (
              <>
                <div className="profile-divider" />
                <div className="profile-subtitle">By blinds</div>
                {profile.account.by_blinds.map(g => (
                  <div key={`${g.small_blind}/${g.big_blind}`} className="profile-row">
                    <span>{g.small_blind ?? '?'}/{g.big_blind ?? '?'}</span>
                    <b>{g.hands} 手 · 胜 {g.wins} · <Chips value={g.net_chips} /></b>
                  </div>
                ))}
              </>
            )}

            {profile.account.recent_hands.length > 0 && (
              <>
                <div className="profile-divider" />
                <div className="profile-subtitle">Recent hands</div>
                <div className="profile-recent">
                  {profile.account.recent_hands.map((h, i) => (
                    <div key={i} className="profile-row">
                      <span className={h.won ? 'lb-pos' : 'lb-neg'}>
                        {h.won ? 'W' : 'L'} {h.board.slice(0, 5).join('') || '—'}
                      </span>
                      <b>{h.net == null ? '—' : <Chips value={h.net} />}</b>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        ) : (
          <div className="profile-note">Guest — lifetime stats are not recorded</div>
        )}
      </div>
    </div>
  );
}
