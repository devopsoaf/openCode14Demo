import { Routes, Route, Navigate } from 'react-router-dom';
import { TooltipProvider } from '@radix-ui/react-tooltip';
import { useIncidentWebSocket } from '@/hooks/useIncidentWebSocket';
import { useAuth } from '@/hooks/useAuth';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Incidents from './pages/Incidents';
import IncidentDetail from './pages/IncidentDetail';
import Alerts from './pages/Alerts';
import Analytics from './pages/Analytics';
import OnCall from './pages/OnCall';
import Notifications from './pages/Notifications';
import Login from './pages/Login';
import NotFound from './pages/NotFound';

function WebSocketProvider() {
	useIncidentWebSocket();
	return null;
}

export default function App() {
	const { isAuthenticated } = useAuth();

	if (!isAuthenticated) {
		return <Login />;
	}

	return (
		<TooltipProvider delayDuration={200}>
			<WebSocketProvider />
			<div className="flex min-h-screen">
				<Sidebar />
				<main className="flex-1 ml-60 overflow-auto">
					<Routes>
						<Route path="/" element={<Dashboard />} />
						<Route path="/incidents" element={<Incidents />} />
						<Route path="/incidents/:incidentId" element={<IncidentDetail />} />
						<Route path="/alerts" element={<Alerts />} />
						<Route path="/analytics" element={<Analytics />} />
						<Route path="/oncall" element={<OnCall />} />
						<Route path="/notifications" element={<Notifications />} />
						<Route path="/login" element={<Navigate to="/" />} />
						<Route path="*" element={<NotFound />} />
					</Routes>
				</main>
			</div>
		</TooltipProvider>
	);
}
