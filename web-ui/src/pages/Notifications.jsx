import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bell, Search, Filter, ChevronLeft, ChevronRight, Mail, MessageSquare, AlertTriangle, Check } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { listNotifications } from '@/services/api';
import { timeAgo } from '@/utils/formatters';
import { cn } from '@/lib/utils';

const CHANNEL_ICONS = { email: Mail, slack: MessageSquare, webhook: AlertTriangle, sms: Bell };

export default function Notifications() {
	const [search, setSearch] = useState('');
	const [page, setPage] = useState(1);
	const pageSize = 15;

	const { data, isLoading } = useQuery({
		queryKey: ['notifications'],
		queryFn: () => listNotifications({ limit: 200 }),
		refetchInterval: 15000,
	});

	const allNotifications = Array.isArray(data) ? data : data?.notifications || [];
	const filtered = allNotifications.filter(n =>
		!search ||
		(n.message || n.subject || n.channel || '').toLowerCase().includes(search.toLowerCase()) ||
		(n.engineer || '').toLowerCase().includes(search.toLowerCase())
	);
	const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
	const paginated = filtered.slice((page - 1) * pageSize, page * pageSize);

	return (
		<div className="space-y-6 fade-in">
			<div>
				<h1 className="text-2xl font-bold tracking-tight">Notifications</h1>
				<p className="text-sm text-muted-foreground mt-1">{filtered.length} notification{filtered.length !== 1 ? 's' : ''} sent</p>
			</div>

			{/* Search */}
			<Card>
				<CardContent className="p-4">
					<div className="relative">
						<Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
						<Input placeholder="Search notifications..." value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-9" />
					</div>
				</CardContent>
			</Card>

			{/* Notifications List */}
			{isLoading ? (
				<div className="space-y-3">{[1, 2, 3, 4, 5].map(i => <div key={i} className="shimmer h-20 rounded-lg" />)}</div>
			) : paginated.length > 0 ? (
				<div className="space-y-3">
					{paginated.map((n, i) => {
						const ChannelIcon = CHANNEL_ICONS[n.channel] || Bell;
						const sent = n.status === 'sent' || n.status === 'delivered';
						return (
							<Card key={n.notification_id || i} className="hover:border-primary/20 transition-colors">
								<CardContent className="p-4">
									<div className="flex items-start gap-4">
										<div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', sent ? 'bg-emerald-500/10' : 'bg-yellow-500/10')}>
											<ChannelIcon className={cn('h-4 w-4', sent ? 'text-emerald-400' : 'text-yellow-400')} />
										</div>
										<div className="flex-1 min-w-0">
											<div className="flex items-center justify-between gap-2">
												<p className="text-sm font-medium truncate">{n.subject || n.message || 'Notification'}</p>
												<span className="text-[10px] text-muted-foreground shrink-0">{timeAgo(n.created_at || n.sent_at)}</span>
											</div>
											<p className="text-xs text-muted-foreground mt-1 line-clamp-2">{n.message || n.body || ''}</p>
											<div className="flex items-center gap-2 mt-2">
												<Badge variant="outline" className="text-[10px]">{n.channel || 'N/A'}</Badge>
												{n.engineer && <span className="text-[10px] text-muted-foreground">&rarr; {n.engineer}</span>}
												<Badge variant={sent ? 'success' : n.status === 'failed' ? 'destructive' : 'secondary'} className="text-[10px] ml-auto">
													{sent && <Check className="mr-1 h-2.5 w-2.5" />}
													{n.status || 'pending'}
												</Badge>
											</div>
										</div>
									</div>
								</CardContent>
							</Card>
						);
					})}
				</div>
			) : (
				<Card>
					<CardContent className="flex flex-col items-center justify-center py-16 text-center">
						<Bell className="h-10 w-10 text-muted-foreground mb-3" />
						<p className="text-sm text-muted-foreground">No notifications found</p>
					</CardContent>
				</Card>
			)}

			{/* Pagination */}
			{totalPages > 1 && (
				<div className="flex items-center justify-between">
					<p className="text-xs text-muted-foreground">Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}</p>
					<div className="flex items-center gap-1">
						<Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><ChevronLeft className="h-4 w-4" /></Button>
						{Array.from({ length: totalPages }, (_, i) => i + 1).slice(Math.max(0, page - 3), page + 2).map(p => (
							<Button key={p} variant={p === page ? 'default' : 'outline'} size="sm" className="w-8" onClick={() => setPage(p)}>{p}</Button>
						))}
						<Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}><ChevronRight className="h-4 w-4" /></Button>
					</div>
				</div>
			)}
		</div>
	);
}
