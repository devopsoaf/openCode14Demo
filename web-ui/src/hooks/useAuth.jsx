import { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

// Demo users — manager sees all incidents, engineers see only their assigned work
const DEMO_USERS = {
	admin: { username: 'admin', name: 'SRE Manager', role: 'admin', email: 'admin@expertmind.io', password: 'admin' },
	alice: { username: 'alice', name: 'Alice Chen', role: 'responder', email: 'omarafidi2005@gmail.com', password: 'alice' },
	bob: { username: 'bob', name: 'Bob Martinez', role: 'responder', email: 'omarafidi2005@gmail.com', password: 'bob' },
	charlie: { username: 'charlie', name: 'Charlie Park', role: 'responder', email: 'omarafidi2005@gmail.com', password: 'charlie' },
	diana: { username: 'diana', name: 'Diana Ross', role: 'responder', email: 'omarafidi2005@gmail.com', password: 'diana' },
	mallory: { username: 'mallory', name: 'Mallory Knight', role: 'responder', email: 'omarafidi2005@gmail.com', password: 'mallory' },
};

export function AuthProvider({ children }) {
	const [user, setUser] = useState(() => {
		try {
			const saved = sessionStorage.getItem('auth_user');
			return saved ? JSON.parse(saved) : null;
		} catch { return null; }
	});

	useEffect(() => {
		if (user) sessionStorage.setItem('auth_user', JSON.stringify(user));
		else sessionStorage.removeItem('auth_user');
	}, [user]);

	const login = (username, password) => {
		const u = DEMO_USERS[username.toLowerCase()];
		if (u && u.password === password) {
			const { password: _, ...userData } = u;
			setUser(userData);
			return true;
		}
		return false;
	};

	const logout = () => setUser(null);

	return (
		<AuthContext.Provider value={{ user, login, logout, isAuthenticated: !!user }}>
			{children}
		</AuthContext.Provider>
	);
}

export const useAuth = () => useContext(AuthContext);
