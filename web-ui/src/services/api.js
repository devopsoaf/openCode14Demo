import axios from 'axios';

const api = axios.create({
	baseURL: '/',
	timeout: Number(import.meta.env.VITE_API_TIMEOUT || 10000),
});

const incidentBase = '/api/incident-management/api/v1';
const oncallBase = '/api/oncall-service/api/v1';
const alertBase = '/api/alert-ingestion/api/v1';
const notificationBase = '/api/notification-service/api/v1';
const aiBase = '/api/ai-analysis/api/v1';

// ─── Incidents ─────────────────────────────────────────────
export async function listIncidents(params = {}) {
	const { data } = await api.get(`${incidentBase}/incidents`, { params });
	return data;
}

export async function getIncident(incidentId) {
	const { data } = await api.get(`${incidentBase}/incidents/${incidentId}`);
	return data;
}

export async function updateIncident(incidentId, payload) {
	const { data } = await api.patch(`${incidentBase}/incidents/${incidentId}`, payload);
	return data;
}

export async function getIncidentAnalytics() {
	const { data } = await api.get(`${incidentBase}/incidents/analytics`);
	return data;
}

export async function getIncidentMetrics(incidentId) {
	const { data } = await api.get(`${incidentBase}/incidents/${incidentId}/metrics`);
	return data;
}

export async function addIncidentNote(incidentId, payload) {
	const { data } = await api.patch(`${incidentBase}/incidents/${incidentId}`, {
		note: payload.content || payload.note,
		author: payload.author || 'Omar Afidi',
	});
	return data;
}

// ─── On-Call ───────────────────────────────────────────────
export async function listSchedules() {
	const { data } = await api.get(`${oncallBase}/schedules`);
	return data;
}

export async function getCurrentOncall(team) {
	const { data } = await api.get(`${oncallBase}/oncall/current`, { params: { team: team || 'platform' } });
	return data;
}

export async function getOncallMetrics() {
	const { data } = await api.get(`${oncallBase}/metrics/oncall`);
	return data;
}

// ─── Alerts ────────────────────────────────────────────────
export async function listAlerts(params = {}) {
	const { data } = await api.get(`${alertBase}/alerts`, { params });
	return data;
}

export async function getCorrelationStats() {
	try {
		const { data } = await api.get('/api/alert-ingestion/metrics', { timeout: 3000, responseType: 'text' });
		// Parse Prometheus metrics for correlation stats
		const lines = data.split('\n');
		const stats = {};
		for (const line of lines) {
			if (line.startsWith('alerts_total ')) stats.total_alerts = parseFloat(line.split(' ')[1]);
			if (line.startsWith('alerts_correlated_total ')) stats.correlated_alerts = parseFloat(line.split(' ')[1]);
			if (line.startsWith('alerts_deduplicated_total ')) stats.deduplicated_alerts = parseFloat(line.split(' ')[1]);
		}
		if (stats.total_alerts > 0 && stats.correlated_alerts != null) {
			stats.noise_reduction_percentage = ((stats.correlated_alerts + (stats.deduplicated_alerts || 0)) / stats.total_alerts) * 100;
		}
		return stats;
	} catch {
		return null;
	}
}

// ─── Notifications ─────────────────────────────────────────
export async function listNotifications(params = {}) {
	try {
		const { data } = await api.get(`${notificationBase}/notifications`, { params });
		return data;
	} catch {
		return [];
	}
}

// ─── Health Checks ─────────────────────────────────────────
export async function checkServiceHealth(service) {
	try {
		const { data } = await api.get(`/api/${service}/health`, { timeout: 3000 });
		return { service, status: 'up', ...data };
	} catch {
		return { service, status: 'down' };
	}
}

export async function checkAllServices() {
	const services = [
		'alert-ingestion',
		'incident-management',
		'oncall-service',
		'notification-service',
		'ai-analysis',
	];
	return Promise.all(services.map(checkServiceHealth));
}

// ─── AI Analysis ───────────────────────────────────────────
export async function getIncidentSuggestions(incidentId) {
	const { data } = await api.get(`${aiBase}/suggestions`, { params: { incident_id: incidentId } });
	return data;
}

export async function analyseAlert(payload) {
	const { data } = await api.post(`${aiBase}/analyze`, payload);
	return data;
}

export async function getKnowledgeBase() {
	const { data } = await api.get(`${aiBase}/knowledge-base`);
	return data;
}

export async function getAiHealth() {
	try {
		const { data } = await api.get('/api/ai-analysis/health', { timeout: 3000 });
		return data;
	} catch {
		return null;
	}
}

export default api;
