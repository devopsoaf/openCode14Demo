import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, AlertTriangle, ChevronLeft, ChevronRight, Eye, CheckCircle2, ShieldAlert, User } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listIncidents, updateIncident } from '@/services/api';
import { timeAgo, severityColor, statusColor, statusDot } from '@/utils/formatters';
import { cn } from '@/lib/utils';

const SEVERITIES = ['all', 'critical', 'high', 'medium', 'low'];
const STATUSES = ['all', 'open', 'acknowledged', 'investigating', 'mitigated', 'resolved', 'closed'];

export default function Incidents() {
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const { user } = useAuth();
	const isAdmin = user?.role === 'admin';
	const [search, setSearch] = useState('');
	const [severity, setSeverity] = useState('all');
	const [status, setStatus] = useState('all');
	const [page, setPage] = useState(1);
	const pageSize = 20;

	const { data, isLoading } = useQuery({
		queryKey: ['incidents', { severity, status, page }],
		queryFn: () => listIncidents({
			limit: 100,
			...(severity !== 'all' && { severity }),
			...(status !== 'all' && { status }),
		}),
		refetchInterval: 5000,
	});

	const updateMutation = useMutation({
		mutationFn: ({ id, payload }) => updateIncident(id, payload),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incidents'] }),
	});

	const allIncidents = Array.isArray(data) ? data : data?.incidents || [];
	// Role-based: engineers only see their assigned incidents
	const roleFiltered = isAdmin ? allIncidents : allIncidents.filter(i => i.assigned_to?.toLowerCase() === user?.username?.toLowerCase());
	const filtered = roleFiltered.filter(i =>
		!search || i.title?.toLowerCase().includes(search.toLowerCase()) ||
		i.service?.toLowerCase().includes(search.toLowerCase()) ||
		i.assigned_to?.toLowerCase().includes(search.toLowerCase())
	);
	const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
	const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

	const handleAction = (e, id, payload) => {
		e.stopPropagation();
		updateMutation.mutate({ id, payload });
	};

	return (
		<div className="space-y-6 fade-in">
			<div className="flex items-center justify-between">
				<div>
					<h1 className="text-2xl font-bold tracking-tight">{isAdmin ? 'All Incidents' : 'My Incidents'}</h1>
					<p className="text-sm text-muted-foreground mt-1">{filtered.length} incident{filtered.length !== 1 ? 's' : ''}{!isAdmin ? ' assigned to you' : ' total'}</p>
				</div>
			</div>

			{/* Filters */}
			<Card>
				<CardContent className="p-4">
					<div className="flex flex-wrap items-center gap-3">
						<div className="relative flex-1 min-w-50">
							<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
							<Input
								placeholder="Search incidents..."
								value={search}
								onChange={e => { setSearch(e.target.value); setPage(1); }}
								className="pl-9"
							/>
						</div>
						<div className="flex items-center gap-2">
							<Filter className="h-4 w-4 text-muted-foreground" />
							<div className="flex gap-1">
								{SEVERITIES.map(s => (
									<button
										key={s}
										onClick={() => { setSeverity(s); setPage(1); }}
										className={cn(
											'rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors border',
											severity === s
												? 'bg-primary/15 text-primary border-primary/30'
												: 'text-muted-foreground hover:text-foreground border-transparent hover:border-border'
										)}
									>
										{s}
									</button>
								))}
							</div>
						</div>
						<div className="flex gap-1">
							{STATUSES.map(s => (
								<button
									key={s}
									onClick={() => { setStatus(s); setPage(1); }}
									className={cn(
										'rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors border',
										status === s
											? 'bg-primary/15 text-primary border-primary/30'
											: 'text-muted-foreground hover:text-foreground border-transparent hover:border-border'
									)}
								>
									{s}
								</button>
							))}
						</div>
					</div>
				</CardContent>
			</Card>

			{/* Table */}
			<Card>
				<CardContent className="p-0">
					{isLoading ? (
						<div className="space-y-3 p-5">{[1, 2, 3, 4, 5].map(i => <div key={i} className="shimmer h-12 w-full" />)}</div>
					) : (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead className="w-10"></TableHead>
									<TableHead>Title</TableHead>
									<TableHead className="w-25">Severity</TableHead>
									<TableHead className="w-27.5">Status</TableHead>
									<TableHead className="w-30">Assigned To</TableHead>
									<TableHead className="w-30">Service</TableHead>
									<TableHead className="w-30">Created</TableHead>
									<TableHead className="w-40 text-right">Actions</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{paginated.map(inc => (
									<TableRow key={inc.incident_id} className="cursor-pointer group" onClick={() => navigate(`/incidents/${inc.incident_id}`)}>
										<TableCell>
											<div className={cn('h-2.5 w-2.5 rounded-full', statusDot[inc.status] || 'bg-zinc-500')} />
										</TableCell>
										<TableCell>
											<div className="flex items-center gap-2">
												<ShieldAlert className={cn('h-3.5 w-3.5 shrink-0', severityColor[inc.severity]?.text || 'text-zinc-400')} />
												<span className="font-medium text-sm">{inc.title}</span>
											</div>
										</TableCell>
										<TableCell>
											<span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase', severityColor[inc.severity]?.badge)}>
												{inc.severity}
											</span>
										</TableCell>
										<TableCell>
											<span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold capitalize', statusColor[inc.status])}>
												{inc.status}
											</span>
										</TableCell>
										<TableCell className="text-xs">
											{inc.assigned_to ? (
												<span className="inline-flex items-center gap-1"><User className="h-3 w-3 text-muted-foreground" />{inc.assigned_to}</span>
											) : (
												<span className="text-muted-foreground italic">unassigned</span>
											)}
										</TableCell>
										<TableCell className="text-xs text-muted-foreground">{inc.service || '—'}</TableCell>
										<TableCell className="text-xs text-muted-foreground">{timeAgo(inc.created_at)}</TableCell>
										<TableCell className="text-right">
											<div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
												{inc.status === 'open' && (
													<Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={e => handleAction(e, inc.incident_id, { status: 'acknowledged' })}>
														<Eye className="mr-1 h-3 w-3" /> Ack
													</Button>
												)}
												{(inc.status === 'open' || inc.status === 'acknowledged' || inc.status === 'investigating') && (
													<Button size="sm" variant="outline" className="h-7 text-[11px] text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10" onClick={e => handleAction(e, inc.incident_id, { status: 'resolved' })}>
														<CheckCircle2 className="mr-1 h-3 w-3" /> Resolve
													</Button>
												)}
											</div>
										</TableCell>
									</TableRow>
								))}
								{paginated.length === 0 && (
									<TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-12">{isAdmin ? 'No incidents match your filters' : 'No incidents assigned to you'}</TableCell></TableRow>
								)}
							</TableBody>
						</Table>
					)}
				</CardContent>
			</Card>

			{/* Pagination */}
			{totalPages > 1 && (
				<div className="flex items-center justify-between">
					<p className="text-xs text-muted-foreground">
						Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}
					</p>
					<div className="flex items-center gap-1">
						<Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
							<ChevronLeft className="h-4 w-4" />
						</Button>
						{Array.from({ length: totalPages }, (_, i) => i + 1).slice(Math.max(0, page - 3), page + 2).map(p => (
							<Button key={p} variant={p === page ? 'default' : 'outline'} size="sm" className="w-8" onClick={() => setPage(p)}>
								{p}
							</Button>
						))}
						<Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
							<ChevronRight className="h-4 w-4" />
						</Button>
					</div>
				</div>
			)}
		</div>
	);
}
