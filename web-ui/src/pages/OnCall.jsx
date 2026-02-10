import { useQuery, useQueries } from '@tanstack/react-query';
import { CalendarClock, User, Phone, Mail, Clock, Shield, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listSchedules, getCurrentOncall, getOncallMetrics } from '@/services/api';
import { formatDate, timeAgo } from '@/utils/formatters';
import { cn } from '@/lib/utils';

const KNOWN_TEAMS = [];  // Will be populated dynamically from schedules

export default function OnCall() {
	const { data: schedules = [], isLoading: schedLoading } = useQuery({
		queryKey: ['schedules'],
		queryFn: listSchedules,
		refetchInterval: 30000,
	});
	const { data: metrics } = useQuery({
		queryKey: ['oncall-metrics'],
		queryFn: getOncallMetrics,
		retry: false,
		refetchInterval: 30000,
	});

	const scheduleList = Array.isArray(schedules) ? schedules : schedules?.schedules || [];

	// Dynamically discover teams from schedules
	const dynamicTeams = [...new Set(scheduleList.map(s => s.team).filter(Boolean))];

	const oncallResults = useQueries({
		queries: dynamicTeams.map(team => ({
			queryKey: ['oncall-current', team],
			queryFn: () => getCurrentOncall(team),
			retry: false,
			enabled: dynamicTeams.length > 0,
		})),
	});

	const oncallList = oncallResults
		.map((q, i) => q.data ? { ...q.data, _team: dynamicTeams[i] } : null)
		.filter(Boolean);

	return (
		<div className="space-y-6 fade-in">
			<div>
				<h1 className="text-2xl font-bold tracking-tight">On-Call Management</h1>
				<p className="text-sm text-muted-foreground mt-1">Current on-call rotations and schedules</p>
			</div>

			{/* Current On-Call */}
			<div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
				{schedLoading ? (
					[1, 2].map(i => <div key={i} className="shimmer h-40 rounded-lg" />)
				) : oncallList.length > 0 ? (
					oncallList.map((oc, i) => (
						<Card key={oc._team || i} className="border-primary/20 bg-primary/2">
							<CardHeader className="pb-2">
								<div className="flex items-center justify-between">
									<CardTitle className="text-sm capitalize">{oc.team || oc._team} Team</CardTitle>
									<Badge variant="success" className="text-[10px]">Active</Badge>
								</div>
							</CardHeader>
							<CardContent className="space-y-3">
								{oc.primary && (
									<div className="flex items-center gap-3">
										<div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15 text-primary font-bold text-sm">
											{(oc.primary.name || 'P')[0]?.toUpperCase()}
										</div>
										<div>
											<p className="font-medium text-sm">{oc.primary.name}</p>
											<p className="text-[11px] text-muted-foreground">{oc.primary.email || oc.primary.role || 'Primary'}</p>
										</div>
										<Badge variant="outline" className="text-[9px] ml-auto">Primary</Badge>
									</div>
								)}
								{oc.secondary && (
									<div className="flex items-center gap-3">
										<div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-muted-foreground font-bold text-sm">
											{(oc.secondary.name || 'S')[0]?.toUpperCase()}
										</div>
										<div>
											<p className="font-medium text-sm">{oc.secondary.name}</p>
											<p className="text-[11px] text-muted-foreground">{oc.secondary.email || oc.secondary.role || 'Secondary'}</p>
										</div>
										<Badge variant="outline" className="text-[9px] ml-auto">Backup</Badge>
									</div>
								)}
								{oc.rotation_type && (
									<div className="flex items-center gap-2 text-xs text-muted-foreground">
										<CalendarClock className="h-3.5 w-3.5" />
										<span className="capitalize">{oc.rotation_type} rotation</span>
									</div>
								)}
							</CardContent>
						</Card>
					))
				) : (
					<Card className="col-span-full">
						<CardContent className="flex flex-col items-center justify-center py-12 text-center">
							<Users className="h-10 w-10 text-muted-foreground mb-3" />
							<p className="text-sm text-muted-foreground">No on-call data available</p>
						</CardContent>
					</Card>
				)}

				{/* Metrics card */}
				{metrics && (
					<Card>
						<CardHeader className="pb-2"><CardTitle className="text-sm">On-Call Metrics</CardTitle></CardHeader>
						<CardContent className="space-y-3">
							{Object.entries(metrics).filter(([k]) => !k.startsWith('_')).map(([key, val]) => (
								<div key={key} className="flex items-center justify-between text-xs">
									<span className="text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span>
									<span className="font-medium">{typeof val === 'number' ? val.toLocaleString() : String(val)}</span>
								</div>
							))}
						</CardContent>
					</Card>
				)}
			</div>

			{/* Schedules Table */}
			<Card>
				<CardHeader className="pb-3">
					<div className="flex items-center justify-between">
						<CardTitle className="text-sm font-semibold">Rotation Schedules</CardTitle>
						<Badge variant="secondary">{scheduleList.length} schedule{scheduleList.length !== 1 ? 's' : ''}</Badge>
					</div>
				</CardHeader>
				<CardContent className="p-0">
					{schedLoading ? (
						<div className="space-y-3 p-5">{[1, 2, 3].map(i => <div key={i} className="shimmer h-12 w-full" />)}</div>
					) : scheduleList.length > 0 ? (
						<Table>
							<TableHeader>
								<TableRow>
									<TableHead>Name</TableHead>
									<TableHead>Team</TableHead>
									<TableHead>Rotation</TableHead>
									<TableHead>Members</TableHead>
									<TableHead>Timezone</TableHead>
									<TableHead className="text-right">Created</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{scheduleList.map((s, i) => (
									<TableRow key={s.id || i}>
										<TableCell className="font-medium text-sm capitalize">{s.team || '—'}</TableCell>
										<TableCell className="text-xs text-muted-foreground">{s.team || '—'}</TableCell>
										<TableCell>
											<Badge variant="outline" className="text-[10px]">{s.rotation_type || 'weekly'}</Badge>
										</TableCell>
										<TableCell>
											<div className="flex items-center gap-1">
												<Users className="h-3 w-3 text-muted-foreground" />
												<span className="text-xs">{s.engineers?.length || '—'}</span>
											</div>
										</TableCell>
										<TableCell className="text-xs text-muted-foreground">{s.timezone || 'UTC'}</TableCell>
										<TableCell className="text-xs text-muted-foreground text-right">{timeAgo(s.created_at)}</TableCell>
									</TableRow>
								))}
							</TableBody>
						</Table>
					) : (
						<div className="flex flex-col items-center justify-center py-12 text-center">
							<CalendarClock className="h-8 w-8 text-muted-foreground mb-2" />
							<p className="text-sm text-muted-foreground">No schedules found</p>
						</div>
					)}
				</CardContent>
			</Card>
		</div>
	);
}
