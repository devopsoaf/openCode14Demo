import { useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Shield, Eye, EyeOff, Users } from 'lucide-react';

const QUICK_LOGINS = [
	{ username: 'admin', label: 'SRE Manager', desc: 'Full dashboard — all incidents', icon: '👨‍💼' },
	{ username: 'alice', label: 'Alice Chen', desc: 'On-call: payment-api', icon: '👩‍💻' },
	{ username: 'bob', label: 'Bob Martinez', desc: 'On-call: auth-service', icon: '👨‍💻' },
	{ username: 'charlie', label: 'Charlie Park', desc: 'On-call: user-service', icon: '🧑‍💻' },
	{ username: 'mallory', label: 'Mallory Knight', desc: 'On-call: api-gateway', icon: '👩‍🔧' },
];

export default function Login() {
	const { login } = useAuth();
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');
	const [showPw, setShowPw] = useState(false);
	const [error, setError] = useState('');
	const [loading, setLoading] = useState(false);

	const handleSubmit = (e) => {
		e.preventDefault();
		setLoading(true);
		setError('');
		setTimeout(() => {
			if (!login(username, password)) {
				setError('Invalid credentials');
			}
			setLoading(false);
		}, 400);
	};

	const handleQuickLogin = (user) => {
		setLoading(true);
		setTimeout(() => {
			login(user, user);
			setLoading(false);
		}, 300);
	};

	return (
		<div className="flex min-h-screen items-center justify-center bg-background p-4">
			<div className="w-full max-w-md fade-in">
				<div className="mb-8 text-center">
					<div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-primary shadow-lg shadow-primary/25">
						<Shield className="h-7 w-7 text-white" />
					</div>
					<h1 className="text-2xl font-bold tracking-tight">ExpertMind</h1>
					<p className="mt-1 text-sm text-muted-foreground">Incident & On-Call Management Platform</p>
				</div>

				<Card className="mb-4">
					<CardHeader className="pb-3">
						<CardTitle className="text-lg">Sign in</CardTitle>
						<CardDescription>Enter your credentials to access the dashboard</CardDescription>
					</CardHeader>
					<CardContent>
						<form onSubmit={handleSubmit} className="space-y-4">
							<div className="space-y-2">
								<label className="text-sm font-medium text-foreground">Username</label>
								<Input
									placeholder="admin"
									value={username}
									onChange={(e) => setUsername(e.target.value)}
									autoFocus
									autoComplete="username"
								/>
							</div>
							<div className="space-y-2">
								<label className="text-sm font-medium text-foreground">Password</label>
								<div className="relative">
									<Input
										type={showPw ? 'text' : 'password'}
										placeholder="••••••"
										value={password}
										onChange={(e) => setPassword(e.target.value)}
										autoComplete="current-password"
									/>
									<button
										type="button"
										onClick={() => setShowPw(!showPw)}
										className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
									>
										{showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
									</button>
								</div>
							</div>
							{error && (
								<p className="text-sm text-destructive">{error}</p>
							)}
							<Button type="submit" className="w-full" disabled={loading}>
								{loading ? <span className="h-4 w-4 rounded-full border-2 border-white/20 border-t-white animate-spin" /> : 'Sign in'}
							</Button>
						</form>
					</CardContent>
				</Card>

				{/* Quick Login */}
				<Card>
					<CardHeader className="pb-2">
						<div className="flex items-center gap-2">
							<Users className="h-4 w-4 text-muted-foreground" />
							<CardTitle className="text-sm">Quick Login — Demo Accounts</CardTitle>
						</div>
					</CardHeader>
					<CardContent className="space-y-2">
						{QUICK_LOGINS.map((u) => (
							<button
								key={u.username}
								onClick={() => handleQuickLogin(u.username)}
								className="w-full flex items-center gap-3 rounded-lg border border-border p-3 text-left hover:bg-accent/50 hover:border-primary/30 transition-colors"
							>
								<span className="text-xl">{u.icon}</span>
								<div className="flex-1 min-w-0">
									<p className="text-sm font-medium">{u.label}</p>
									<p className="text-[11px] text-muted-foreground">{u.desc}</p>
								</div>
								<span className="text-[10px] text-muted-foreground font-mono">{u.username}/{u.username}</span>
							</button>
						))}
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
