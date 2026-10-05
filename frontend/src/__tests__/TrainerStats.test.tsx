import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Trainer from '../pages/Trainer';

const SCENARIOS = {
  scenarios: [
    {
      id: 'preflop-btn-premium', title: '翻前 BTN 强牌', description: '描述',
      category: 'preflop_range', difficulty: 1,
    },
  ],
};

const STATS = {
  total_attempts: 12,
  avg_score: 76.5,
  optimal_rate: 0.667,
  categories: [
    { category: 'river_decision', attempts: 6, avg_score: 65, optimal_rate: 0.5 },
    { category: 'preflop_range', attempts: 6, avg_score: 88, optimal_rate: 0.83 },
  ],
  recent: [{ scenario_id: 'x', score: 80, is_optimal: true, created_at: '' }],
};

const MISTAKES = {
  mistakes: [
    {
      scenario_id: 'river-bluff-spot', title: '河牌诈唬位', category: 'river_decision',
      difficulty: 3, last_score: 40, attempts: 2, last_tried_at: '2026-10-05T10:00:00',
    },
  ],
};

function stubFetch(opts: { stats?: unknown; mistakes?: unknown } = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.includes('/stats')) return 'stats' in opts ? opts.stats : STATS;
      if (url.includes('/mistakes')) return 'mistakes' in opts ? opts.mistakes : MISTAKES;
      if (url.includes('/importable-hands')) return { hands: [] };
      return SCENARIOS;
    },
  })));
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/trainer']}>
      <Routes>
        <Route path="/trainer" element={<Trainer />} />
        <Route path="/trainer/:scenarioId" element={<div>SCENARIO_PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

test('guest (no token) sees neither stats nor mistake book', async () => {
  stubFetch({ stats: STATS, mistakes: MISTAKES });
  renderPage();
  await waitFor(() => expect(screen.getByText('翻前 BTN 强牌')).toBeInTheDocument());
  expect(screen.queryByText('训练统计')).not.toBeInTheDocument();
  expect(screen.queryByText(/错题本/)).not.toBeInTheDocument();
});

test('logged-in renders overview numbers and per-category bars', async () => {
  localStorage.setItem('authToken', 't.1');
  stubFetch();
  const { container } = renderPage();
  await waitFor(() => expect(screen.getByText('训练统计')).toBeInTheDocument());
  expect(screen.getByText('12')).toBeInTheDocument();
  expect(screen.getByText('76.5')).toBeInTheDocument();
  expect(screen.getByText('67%')).toBeInTheDocument();           // optimal rate
  const bars = container.querySelectorAll('.trainer-weak-list .fb-bar-row');
  expect(bars).toHaveLength(2);
  // Weakest category first (sorted by avg score asc from the server)
  expect(bars[0]).toHaveTextContent('河牌决策');
  expect(bars[0].querySelector('.fb-bar-fill')).toHaveStyle({ width: '65%' });
});

test('mistake book lists entries and clicking navigates to the scenario', async () => {
  localStorage.setItem('authToken', 't.1');
  stubFetch();
  renderPage();
  await waitFor(() => expect(screen.getByText('河牌诈唬位')).toBeInTheDocument());
  expect(screen.getByText(/上次 40 分/)).toBeInTheDocument();
  expect(screen.getByText(/已练 2 次/)).toBeInTheDocument();

  fireEvent.click(screen.getByText('河牌诈唬位'));
  expect(await screen.findByText('SCENARIO_PAGE')).toBeInTheDocument();
});

test('stats hidden when account has zero attempts', async () => {
  localStorage.setItem('authToken', 't.1');
  stubFetch({ stats: { total_attempts: 0, avg_score: null, optimal_rate: null, categories: [] } });
  renderPage();
  await waitFor(() => expect(screen.getByText('翻前 BTN 强牌')).toBeInTheDocument());
  expect(screen.queryByText('训练统计')).not.toBeInTheDocument();
});
