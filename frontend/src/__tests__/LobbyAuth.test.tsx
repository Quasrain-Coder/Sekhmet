import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Lobby from '../pages/Lobby';

const PROFILE = { username: 'alice', stats: { hands: 12, wins: 5, net_chips: 340 } };

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

test('login stores the token and shows the personal profile', async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/game/tables') {
      return { ok: true, json: async () => ({ tables: [] }) };
    }
    if (url === '/api/auth/login') {
      return {
        ok: true,
        json: async () => ({ token: 'tok-1', username: 'alice' }),
      };
    }
    if (url.startsWith('/api/auth/me')) {
      return { ok: true, json: async () => PROFILE };
    }
    throw new Error(`unexpected fetch ${url} ${init?.method ?? 'GET'}`);
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <MemoryRouter>
      <Lobby />
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'alice' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'secret123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Login' }));

  await waitFor(() => {
    expect(localStorage.getItem('authToken')).toBe('tok-1');
  });
  // profile panel shows the account and its stats
  expect(await screen.findByText('👤 alice')).toBeTruthy();
  expect(screen.getByText(/Hands 12 · Wins 5/)).toBeTruthy();
  // the login form is gone, logout is available
  expect(screen.queryByRole('button', { name: 'Login' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Logout' })).toBeTruthy();
});

test('register flow works and can be toggled from the login form', async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/game/tables') {
      return { ok: true, json: async () => ({ tables: [] }) };
    }
    if (url === '/api/auth/register') {
      return { ok: true, json: async () => ({ token: 'tok-2', username: 'bob' }) };
    }
    if (url.startsWith('/api/auth/me')) {
      return { ok: true, json: async () => ({ username: 'bob', stats: { hands: 0, wins: 0, net_chips: 0 } }) };
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <MemoryRouter>
      <Lobby />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole('button', { name: 'No account? Register' }));
  fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: 'bob' } });
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'secret123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Register' }));

  await waitFor(() => {
    expect(localStorage.getItem('authToken')).toBe('tok-2');
  });
  expect(await screen.findByText('👤 bob')).toBeTruthy();
});

test('guest mode shows the login form and logout clears the session', async () => {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/game/tables') {
      return { ok: true, json: async () => ({ tables: [] }) };
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  localStorage.setItem('authToken', 'tok-old');
  localStorage.setItem('authUser', 'alice');

  render(
    <MemoryRouter>
      <Lobby />
    </MemoryRouter>,
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Logout' }));
  await waitFor(() => {
    expect(localStorage.getItem('authToken')).toBeNull();
  });
  expect(screen.getByRole('button', { name: 'Login' })).toBeTruthy();
});
