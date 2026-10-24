import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { StudentLayout, TeacherLayout } from './components/Layout';
import { Loading } from './components/ui';
import { useAuth } from './lib/auth';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import NotFound from './pages/NotFound';
import Dashboard from './pages/student/Dashboard';
import Chat from './pages/student/Chat';
import CheckIn from './pages/student/CheckIn';
import Wellness from './pages/student/Wellness';
import Activities from './pages/student/Activities';
import ActivityPlayer from './pages/student/ActivityPlayer';
import Progress from './pages/student/Progress';
import Emergency from './pages/student/Emergency';
import Settings from './pages/student/Settings';
import TeacherHome from './pages/teacher/TeacherHome';
import ClassAnalytics from './pages/teacher/ClassAnalytics';

function RequireRole({ role, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading label="Checking your session…" />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (user.role !== role) return <Navigate to={user.role === 'teacher' ? '/teacher' : '/app'} replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/teacher/login" element={<Login teacher />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/app"
        element={
          <RequireRole role="student">
            <StudentLayout />
          </RequireRole>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<Chat />} />
        <Route path="chat/:conversationId" element={<Chat />} />
        <Route path="checkin" element={<CheckIn />} />
        <Route path="wellness" element={<Wellness />} />
        <Route path="activities" element={<Activities />} />
        <Route path="activities/:activityId" element={<ActivityPlayer />} />
        <Route path="progress" element={<Progress />} />
        <Route path="support" element={<Emergency />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route
        path="/teacher"
        element={
          <RequireRole role="teacher">
            <TeacherLayout />
          </RequireRole>
        }
      >
        <Route index element={<TeacherHome />} />
        <Route path="classes/:classId" element={<ClassAnalytics />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
