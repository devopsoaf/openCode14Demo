import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
	AlertTriangle, Clock, CheckCircle2, Timer, Eye,
	Zap, ArrowRight, ShieldAlert, TrendingDown, User, Cpu, HardDrive, Wifi, Database, Globe, Server
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listIncidents, getIncidentAnalytics, checkAllServices, listAlerts } from '@/services/api';
import { timeAgo, formatSeconds, severityColor, statusColor } from '@/utils/formatters';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/utils';

function StatCard({ title, value, subtitle, icon: Icon, iconColor }) {
	return (
		<Card className="relative overflow-hidden">
			<CardContent className="p-5">
				<div className="flex items-start justify-between">
					<div className="space-y-1">
						<p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">{title}</p>
						<p className="text-2xl font-bold tracking-tight">{value}</p>
						{subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}
					</div>
					<div className={cn('flex h-10 w-10 items-center justify-center rounded-xl', iconColor || 'bg-primary/10')}>
						<Icon className={cn('h-5 w-5',
							iconColor?.includes('red') ? 'text-red-400' :
								iconColor?.includes('yellow') ? 'text-yellow-400' :
									iconColor?.includes('emerald') ? 'text-emerald-400' :
										iconColor?.includes('blue') ? 'text-blue-400' :
											iconColor?.includes('purple') ? 'text-purple-400' :
												'text-primary'
						)} />
					</div>
				</div>
			</CardContent>
		</Card>
	);
}

export default function Dashboard() {
	const navigate = useNavigate();
	const { user } = useAuth();
	const isAdmin = user?.role === 'admin';

	const { data: incidents = [], isLoading: incLoading } = useQuery({
		queryKey: ['incidents'],
		queryFn: () => listIncidents({ limit: 50 }),
		refetchInterval: 5000,
	});
	const { data: analytics, isLoading: analyticsLoading } = useQuery({
		queryKey: ['analytics'],
		queryFn: getIncidentAnalytics,
		refetchInterval: 10000,
	});
	const { data: services = [] } = useQuery({
		queryKey: ['services'],
		queryFn: checkAllServices,
		refetchInterval: 15000,
	});
	const { data: alerts = [] } = useQuery({
		queryKey: ['alerts-recent'],
		queryFn: () => listAlerts({ limit: 50 }),
		refetchInterval: 5000,
	});

	const incidentList = Array.isArray(incidents) ? incidents : incidents?.incidents || [];
	// Role-based filtering: engineers see only their assigned incidents
	const myIncidents = isAdmin
		? incidentList
		: incidentList.filter(i => i.assigned_to?.toLowerCase() === user?.username?.toLowerCase());
	const openCount = myIncidents.filter(i => i.status === 'open').length;
	const ackedCount = myIncidents.filter(i => i.status === 'acknowledged').length;
	const resolvedCount = myIncidents.filter(i => i.status === 'resolved' || i.status === 'closed').length;
	const criticalCount = myIncidents.filter(i => i.severity === 'critical' && i.status === 'open').length;
	const mtta = analytics?.avg_mtta_seconds;
	const mttr = analytics?.avg_mttr_seconds;
	const recentIncidents = myIncidents.slice(0, 8);
	const alertList = Array.isArray(alerts) ? alerts : alerts?.alerts || [];

	// Group alerts by category
	const CATEGORY_ICONS = { CPU: Cpu, Memory: Server, Disk: HardDrive, Network: Wifi, Database: Database, HTTP: Globe, 'SSL/TLS': ShieldAlert, Kubernetes: Server, Queue: Database };
	const alertsByCategory = alertList.reduce((acc, a) => {
		const cat = a.labels?.category || 'Other';
		if (!acc[cat]) acc[cat] = [];
		acc[cat].push(a);
		return acc;
	}, {});

	return (
		<div className="space-y-6 fade-in p-6">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-2xl font-bold tracking-tight">
						{isAdmin ? 'Command Center' : `Welcome, ${user?.name || user?.username}`}
					</h1>
					<p className="text-sm text-muted-foreground mt-1">
						{isAdmin ? 'Real-time overview of all incidents, alerts, and platform health' : 'Your assigned incidents and on-call alerts'}
					</p>
				</div>
				{!isAdmin && (
					<Badge variant="outline" className="text-xs gap-1"><User className="h-3 w-3" /> {user?.username} — On-Call Responder</Badge>
				)}
			</div>

			{/* Stats */}
			<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
				<StatCard title="Open" value={incLoading ? '—' : openCount} subtitle={criticalCount > 0 ? `${criticalCount} critical` : undefined} icon={AlertTriangle} iconColor="bg-red-500/10" />
				<StatCard title="Acknowledged" value={incLoading ? '—' : ackedCount} icon={Eye} iconColor="bg-yellow-500/10" />
				<StatCard title="Resolved" value={incLoading ? '—' : resolvedCount} icon={CheckCircle2} iconColor="bg-emerald-500/10" />
				<StatCard title="MTTA" value={analyticsLoading ? '—' : formatSeconds(mtta)} subtitle="Avg acknowledge" icon={Timer} iconColor="bg-blue-500/10" />
				<StatCard title="MTTR" value={analyticsLoading ? '—' : formatSeconds(mttr)} subtitle="Avg resolve" icon={Clock} iconColor="bg-purple-500/10" />
			</div>


			{/* Main Grid */}
			<div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
				{/* Recent Incidents */}
				<Card className="lg:col-span-2">
					<CardHeader className="pb-3">
						<div className="flex items-center justify-between">
							<CardTitle className="text-sm font-semibold">Recent Incidents</CardTitle>
							<Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/incidents')}>View all <ArrowRight className="ml-1 h-3 w-3" /></Button>
						</div>
					</CardHeader>
					<CardContent className="p-0">
						{incLoading ? (
							<div className="space-y-3 p-5">{[1, 2, 3].map(i => <div key={i} className="shimmer h-10 w-full" />)}</div>
						) : (
							<Table>
								<TableHeader>
									<TableRow>
										<TableHead>Title</TableHead>
										<TableHead className="w-28">Assigned To</TableHead>
										<TableHead className="w-22.5">Severity</TableHead>
										<TableHead className="w-25">Status</TableHead>
										<TableHead className="w-30 text-right">When</TableHead>
									</TableRow>
								</TableHeader>
								<TableBody>
									{recentIncidents.map(inc => (
										<TableRow key={inc.incident_id} className="cursor-pointer hover:bg-accent/50 transition-colors" onClick={() => navigate(`/incidents/${inc.incident_id}`)}>
											<TableCell>
												<div className="flex items-center gap-2">
													<ShieldAlert className={cn('h-3.5 w-3.5 shrink-0', severityColor[inc.severity]?.text || 'text-zinc-400')} />
													<span className="font-medium text-sm truncate max-w-75">{inc.title}</span>
												</div>
											</TableCell>
											<TableCell>
												{inc.assigned_to ? (
													<span className="inline-flex items-center gap-1 text-xs"><User className="h-3 w-3 text-muted-foreground" />{inc.assigned_to}</span>
												) : (
													<span className="text-xs text-muted-foreground italic">unassigned</span>
												)}
											</TableCell>
											<TableCell><span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase', severityColor[inc.severity]?.badge)}>{inc.severity}</span></TableCell>
											<TableCell><span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold capitalize', statusColor[inc.status])}>{inc.status}</span></TableCell>
											<TableCell className="text-right text-xs text-muted-foreground">{timeAgo(inc.created_at)}</TableCell>
										</TableRow>
									))}
									{recentIncidents.length === 0 && (
										<TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-8">{isAdmin ? 'No incidents found' : 'No incidents assigned to you'}</TableCell></TableRow>
									)}
								</TableBody>
							</Table>
						)}
					</CardContent>
				</Card>

				{/* Alerts by Category */}
				<Card>
					<CardHeader className="pb-3">
						<div className="flex items-center justify-between">
							<CardTitle className="text-sm font-semibold">Alerts by Category</CardTitle>
							<Button variant="ghost" size="sm" className="text-xs" onClick={() => navigate('/alerts')}>View all <ArrowRight className="ml-1 h-3 w-3" /></Button>
						</div>
					</CardHeader>
					<CardContent>
						{Object.keys(alertsByCategory).length === 0 ? (
							<p className="text-center text-sm text-muted-foreground py-4">No recent alerts</p>
						) : (
							<div className="space-y-4">
								{Object.entries(alertsByCategory).sort((a, b) => b[1].length - a[1].length).map(([cat, catAlerts]) => {
									const IconComp = CATEGORY_ICONS[cat] || Zap;
									const critCount = catAlerts.filter(a => a.severity === 'critical').length;
									return (
										<div key={cat} className="rounded-lg border border-border p-3">
											<div className="flex items-center justify-between mb-2">
												<div className="flex items-center gap-2">
													<div className={cn('rounded-md p-1.5', critCount > 0 ? 'bg-red-500/10' : 'bg-blue-500/10')}>
														<IconComp className={cn('h-3.5 w-3.5', critCount > 0 ? 'text-red-400' : 'text-blue-400')} />
													</div>
													<span className="text-xs font-semibold">{cat}</span>
												</div>
												<div className="flex items-center gap-1.5">
													{critCount > 0 && <span className="rounded-md bg-red-500/10 border border-red-500/20 px-1.5 py-0.5 text-[9px] font-bold text-red-400">{critCount} CRIT</span>}
													<Badge variant="secondary" className="text-[10px]">{catAlerts.length}</Badge>
												</div>
											</div>
											<div className="space-y-1.5">
												{catAlerts.slice(0, 3).map((a, i) => (
													<div key={a.alert_id || i} className="flex items-center gap-2 text-[11px]">
														<span className={cn('h-1.5 w-1.5 rounded-full shrink-0', a.severity === 'critical' ? 'bg-red-400' : a.severity === 'warning' ? 'bg-yellow-400' : 'bg-blue-400')} />
														<span className="truncate text-muted-foreground">{a.alert_name || a.message || 'Alert'}</span>
														<span className="ml-auto text-[10px] text-muted-foreground/60 shrink-0">{timeAgo(a.created_at || a.timestamp)}</span>
													</div>
												))}
												{catAlerts.length > 3 && <p className="text-[10px] text-muted-foreground/60 pl-3.5">+{catAlerts.length - 3} more</p>}
											</div>
										</div>
									);
								})}
							</div>
						)}
					</CardContent>
				</Card>
			</div>
		</div>
	);
}
