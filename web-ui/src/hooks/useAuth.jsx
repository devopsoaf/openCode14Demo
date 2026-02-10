import { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

// Demo user — single account for the platform
const DEMO_USERS = {
	oafidi: { username: 'oafidi', name: 'Omar Afidi', role: 'admin', email: 'omarafidi2005@gmail.com', password: 'oafidi' },
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
