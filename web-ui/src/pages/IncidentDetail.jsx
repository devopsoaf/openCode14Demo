import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
	ArrowLeft, Eye, CheckCircle2, Clock, AlertTriangle, Brain,
	MessageSquare, Send, ExternalLink, Zap, Lightbulb, BookOpen,
	ChevronDown, ChevronUp, Copy, Check
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { getIncident, updateIncident, addIncidentNote, getIncidentSuggestions } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import { timeAgo, formatDate, formatSeconds, severityColor, statusColor, statusDot } from '@/utils/formatters';
import { cn } from '@/lib/utils';

function CopyButton({ text }) {
	const [copied, setCopied] = useState(false);
	const copy = () => {
		navigator.clipboard.writeText(text);
		setCopied(true);
		setTimeout(() => setCopied(false), 1500);
	};
	return (
		<button onClick={copy} className="p-1 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground">
			{copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
		</button>
	);
}

export default function IncidentDetail() {
	const { incidentId } = useParams();
	const navigate = useNavigate();
	const queryClient = useQueryClient();
	const { user } = useAuth();
	const [noteText, setNoteText] = useState('');
	const [showAi, setShowAi] = useState(true);

	const { data: incident, isLoading } = useQuery({
		queryKey: ['incident', incidentId],
		queryFn: () => getIncident(incidentId),
	});

	const { data: suggestions, isLoading: aiLoading } = useQuery({
		queryKey: ['suggestions', incidentId],
		queryFn: () => getIncidentSuggestions(incidentId),
		enabled: !!incidentId,
		retry: false,
	});

	const statusMutation = useMutation({
		mutationFn: (payload) => updateIncident(incidentId, payload),
		onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incident', incidentId] }),
	});

	const noteMutation = useMutation({
		mutationFn: (payload) => addIncidentNote(incidentId, payload),
		onSuccess: () => {
			queryClient.invalidateQueries({ queryKey: ['incident', incidentId] });
			setNoteText('');
		},
	});

	const handleAddNote = (e) => {
		e.preventDefault();
		if (!noteText.trim()) return;
		noteMutation.mutate({ content: noteText.trim(), author: user?.name || user?.username || 'Omar Afidi' });
	};

	if (isLoading) {
		return (
			<div className="space-y-4 fade-in">
				<div className="shimmer h-8 w-64" />
				<div className="shimmer h-100 w-full" />
			</div>
		);
	}

	if (!incident) {
		return (
			<div className="flex flex-col items-center justify-center py-20 text-center">
				<AlertTriangle className="h-12 w-12 text-muted-foreground mb-4" />
				<h2 className="text-lg font-semibold">Incident not found</h2>
				<Button variant="outline" className="mt-4" onClick={() => navigate('/incidents')}>Back to incidents</Button>
			</div>
		);
	}

	// Normalise notes: backend may store as plain strings or as objects
	const rawNotes = incident.notes || [];
	const notes = rawNotes.map(n => {
		if (typeof n === 'string') {
			// Legacy format: "[2026-02-10T15:48:14+00:00] Some text"
			const tsMatch = n.match(/^\[([^\]]+)\]\s*(.*)/);
			return tsMatch
				? { author: 'System', content: tsMatch[2], created_at: tsMatch[1] }
				: { author: 'System', content: n, created_at: null };
		}
		return n; // already an object {author, content, created_at}
	});
	const linkedAlerts = incident.linked_alert_ids || incident.alert_ids || [];
	const isOpen = incident.status === 'open';
	const isAcked = incident.status === 'acknowledged';
	const canResolve = ['open', 'acknowledged', 'investigating'].includes(incident.status);

	// AI endpoint returns an array of {root_cause,solution,confidence,source,matched_pattern}
	const rawSuggestions = suggestions?.suggestions || suggestions;
	const suggestionArr = Array.isArray(rawSuggestions) ? rawSuggestions : rawSuggestions ? [rawSuggestions] : [];
	// Deduplicate by root_cause
	const seen = new Set();
	const uniqueSuggestions = suggestionArr.filter(s => {
		const key = s.root_cause || s.solution || JSON.stringify(s);
		if (seen.has(key)) return false;
		seen.add(key);
		return true;
	});
	const hasSuggestions = uniqueSuggestions.length > 0;

	return (
		<div className="space-y-6 fade-in">
			{/* Header */}
			<div className="flex items-start gap-4">
				<Button variant="ghost" size="icon" onClick={() => navigate('/incidents')}>
					<ArrowLeft className="h-5 w-5" />
				</Button>
				<div className="flex-1 min-w-0">
					<div className="flex items-center gap-3 flex-wrap">
						<h1 className="text-xl font-bold tracking-tight">{incident.title}</h1>
						<span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase', severityColor[incident.severity]?.badge)}>{incident.severity}</span>
						<span className={cn('inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[10px] font-semibold capitalize', statusColor[incident.status])}>
							<span className={cn('h-1.5 w-1.5 rounded-full', statusDot[incident.status])} />
							{incident.status}
						</span>
					</div>
					<p className="mt-1 text-sm text-muted-foreground">
						ID: {incident.incident_id} &middot; Created {timeAgo(incident.created_at)} &middot; Service: {incident.service || '—'}
					</p>
				</div>
				<div className="flex items-center gap-2 shrink-0">
					{isOpen && (
						<Button variant="outline" size="sm" onClick={() => statusMutation.mutate({ status: 'acknowledged' })} disabled={statusMutation.isPending}>
							<Eye className="mr-1.5 h-3.5 w-3.5" /> Acknowledge
						</Button>
					)}
					{canResolve && (
						<Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => statusMutation.mutate({ status: 'resolved' })} disabled={statusMutation.isPending}>
							<CheckCircle2 className="mr-1.5 h-3.5 w-3.5" /> Resolve
						</Button>
					)}
				</div>
			</div>

			<div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
				{/* Main Content */}
				<div className="lg:col-span-2 space-y-6">
					{/* Description */}
					{incident.description && (
						<Card>
							<CardHeader className="pb-2"><CardTitle className="text-sm">Description</CardTitle></CardHeader>
							<CardContent><p className="text-sm text-muted-foreground whitespace-pre-wrap">{incident.description}</p></CardContent>
						</Card>
					)}

					{/* AI Suggestions */}
					<Card className="border-primary/20 bg-primary/2">
						<CardHeader className="pb-2">
							<div className="flex items-center justify-between">
								<div className="flex items-center gap-2">
									<Brain className="h-4 w-4 text-primary" />
									<CardTitle className="text-sm">AI Analysis & Suggestions</CardTitle>
								</div>
								<Button variant="ghost" size="sm" className="h-7" onClick={() => setShowAi(!showAi)}>
									{showAi ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
								</Button>
							</div>
						</CardHeader>
						{showAi && (
							<CardContent>
								{aiLoading ? (
									<div className="space-y-2">
										<div className="shimmer h-4 w-3/4" />
										<div className="shimmer h-4 w-1/2" />
										<div className="shimmer h-4 w-2/3" />
									</div>
								) : hasSuggestions ? (
									<div className="space-y-4">
										{uniqueSuggestions.map((s, i) => (
											<div key={i} className="rounded-lg border border-border bg-card p-4 space-y-3">
												<div className="flex items-center gap-2 justify-between">
													<div className="flex items-center gap-2">
														<Lightbulb className="h-4 w-4 text-yellow-400" />
														<p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
															{s.source === 'knowledge_base' ? 'Knowledge Base' : s.source || 'AI'} Match
														</p>
													</div>
													{s.confidence != null && (
														<div className="flex items-center gap-2 text-xs text-muted-foreground">
															<div className="h-1.5 w-20 rounded-full bg-secondary overflow-hidden">
																<div className="h-full rounded-full bg-primary" style={{ width: `${Math.round(s.confidence * 100)}%` }} />
															</div>
															<span>{Math.round(s.confidence * 100)}%</span>
														</div>
													)}
												</div>
												{s.root_cause && <p className="text-sm font-medium">{s.root_cause}</p>}
												{s.solution && (
													<div className="text-sm text-muted-foreground whitespace-pre-wrap">{s.solution}</div>
												)}
												{s.matched_pattern && (
													<p className="text-[10px] text-muted-foreground/60 italic">Pattern: {s.matched_pattern}</p>
												)}
											</div>
										))}
									</div>
								) : (
									<p className="text-sm text-muted-foreground">No AI suggestions available for this incident.</p>
								)}
							</CardContent>
						)}
					</Card>

					{/* Notes / Timeline */}
					<Card>
						<CardHeader className="pb-3">
							<CardTitle className="text-sm flex items-center gap-2">
								<MessageSquare className="h-4 w-4" /> Notes & Timeline
							</CardTitle>
						</CardHeader>
						<CardContent className="space-y-4">
							{/* Add note form */}
							<form onSubmit={handleAddNote} className="flex gap-2">
								<Input
									placeholder="Add a note..."
									value={noteText}
									onChange={e => setNoteText(e.target.value)}
									className="flex-1"
								/>
								<Button type="submit" size="sm" disabled={!noteText.trim() || noteMutation.isPending}>
									<Send className="h-4 w-4" />
								</Button>
							</form>

							{/* Notes list */}
							<div className="space-y-3">
								{notes.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">No notes yet</p>}
								{notes.map((note, i) => (
									<div key={note.id || i} className="rounded-lg border border-border p-3">
										<div className="flex items-center justify-between mb-1.5">
											<span className="text-xs font-medium">{note.author || 'Unknown'}</span>
											<span className="text-[10px] text-muted-foreground">{timeAgo(note.created_at)}</span>
										</div>
										<p className="text-sm text-muted-foreground">{note.content}</p>
									</div>
								))}
							</div>
						</CardContent>
					</Card>
				</div>

				{/* Sidebar */}
				<div className="space-y-6">
					{/* Properties */}
					<Card>
						<CardHeader className="pb-3"><CardTitle className="text-sm">Properties</CardTitle></CardHeader>
						<CardContent className="space-y-3">
							{[
								['Status', <span className={cn('inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[10px] font-semibold capitalize', statusColor[incident.status])}><span className={cn('h-1.5 w-1.5 rounded-full', statusDot[incident.status])} />{incident.status}</span>],
								['Severity', <span className={cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase', severityColor[incident.severity]?.badge)}>{incident.severity}</span>],
								['Service', incident.service || '—'],
								['Source', incident.source || '—'],
								['Assigned To', incident.assigned_to || 'Unassigned'],
								['Created', formatDate(incident.created_at)],
								['Acknowledged', incident.acknowledged_at ? formatDate(incident.acknowledged_at) : '—'],
								['Resolved', incident.resolved_at ? formatDate(incident.resolved_at) : '—'],
							].map(([label, value]) => (
								<div key={label} className="flex items-center justify-between py-1">
									<span className="text-xs text-muted-foreground">{label}</span>
									<span className="text-xs font-medium">{value}</span>
								</div>
							))}
						</CardContent>
					</Card>

					{/* Linked Alerts */}
					{linkedAlerts.length > 0 && (
						<Card>
							<CardHeader className="pb-3">
								<CardTitle className="text-sm flex items-center gap-2">
									<Zap className="h-4 w-4 text-yellow-400" /> Linked Alerts
									<Badge variant="secondary" className="ml-auto text-[10px]">{linkedAlerts.length}</Badge>
								</CardTitle>
							</CardHeader>
							<CardContent>
								<div className="space-y-2">
									{linkedAlerts.map((alertId, i) => (
										<div key={alertId || i} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs">
											<Zap className="h-3 w-3 text-yellow-400 shrink-0" />
											<span className="truncate font-mono text-muted-foreground">{alertId}</span>
										</div>
									))}
								</div>
							</CardContent>
						</Card>
					)}

					{/* Metrics */}
					<Card>
						<CardHeader className="pb-3"><CardTitle className="text-sm flex items-center gap-2"><Clock className="h-4 w-4" /> Timeline Metrics</CardTitle></CardHeader>
						<CardContent className="space-y-3">
							{incident.acknowledged_at && incident.created_at && (
								<div className="flex justify-between text-xs">
									<span className="text-muted-foreground">Time to Ack</span>
									<span className="font-medium">{formatSeconds((new Date(incident.acknowledged_at) - new Date(incident.created_at)) / 1000)}</span>
								</div>
							)}
							{incident.resolved_at && incident.created_at && (
								<div className="flex justify-between text-xs">
									<span className="text-muted-foreground">Time to Resolve</span>
									<span className="font-medium">{formatSeconds((new Date(incident.resolved_at) - new Date(incident.created_at)) / 1000)}</span>
								</div>
							)}
							{!incident.acknowledged_at && !incident.resolved_at && (
								<p className="text-xs text-muted-foreground text-center">No timeline data yet</p>
							)}
						</CardContent>
					</Card>
				</div>
			</div>
		</div>
	);
}
