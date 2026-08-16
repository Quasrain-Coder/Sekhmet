export interface ProfileAccount {
  username: string;
  hands: number;
  wins: number;
  net_chips: number;
}

export interface ProfileData {
  name: string;
  is_human: boolean;
  bot_level: number | null;
  // Table context — absent for the lobby's own-profile view.
  stack?: number;
  buyin?: number;
  hands: number;
  wins: number;
  net_chips: number;
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
            <div className="profile-row"><span>Total buy-in</span><b>{profile.buyin ?? 0}</b></div>
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
          </>
        ) : (
          <div className="profile-note">Guest — lifetime stats are not recorded</div>
        )}
      </div>
    </div>
  );
}
