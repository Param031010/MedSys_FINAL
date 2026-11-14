import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUser } from "@clerk/clerk-react";
import { PageHeader } from "@/components/PageHeader";
import { fetchCommandCenter } from "@/services/clinicalService";
import type { CommandCenterData } from "@/types";
import type { LucideIcon } from "lucide-react";
import {
  Users,
  Calendar,
  AlertTriangle,
  ArrowRight,
  Activity,
  Command,
  CheckCircle2,
  Clock,
  ExternalLink,
} from "lucide-react";

interface KpiCardProps {
  label: string;
  value: number | string;
  hint: string;
  icon: LucideIcon;
  accent: "teal" | "indigo" | "clay";
  onClick: () => void;
}

const ACCENT_CLASSES: Record<KpiCardProps["accent"], { icon: string; value: string; hover: string }> = {
  teal: { icon: "text-teal-deep", value: "text-ink", hover: "hover:border-teal-deep" },
  indigo: { icon: "text-indigo-thread", value: "text-ink", hover: "hover:border-indigo-thread" },
  clay: { icon: "text-clay-alert", value: "text-clay-alert", hover: "hover:border-clay-alert" },
};

function KpiCard({ label, value, hint, icon: Icon, accent, onClick }: KpiCardProps) {
  const a = ACCENT_CLASSES[accent];
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex min-h-[112px] flex-col justify-between rounded-2xl border border-hairline bg-surface-card p-4 text-left shadow-xs transition-all hover:shadow-md sm:p-5 ${a.hover}`}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-stone">
          {label}
        </span>
        <Icon className={`h-4 w-4 shrink-0 ${a.icon}`} />
      </div>
      <p className={`num font-display text-3xl font-semibold leading-none ${a.value}`}>{value}</p>
      <div className="flex items-center justify-between font-mono text-[11px] text-stone">
        <span className="truncate">{hint}</span>
        <ArrowRight className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </button>
  );
}

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export const DoctorCommandCenter: React.FC = () => {
  const { user } = useUser();
  const [data, setData] = useState<CommandCenterData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const doctorDisplayName =
    user?.fullName ||
    (user?.firstName ? `Dr. ${user.firstName} ${user.lastName || ""}`.trim() : "") ||
    "Dr. Clinician";

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchCommandCenter();
      setData(res);
    } catch (err: any) {
      console.error("Failed to load Command Center", err);
      setError("Failed to connect to the backend clinical server.");
    } finally {
      setLoading(false);
    }
  };

  const priorityAlerts = useMemo(
    () =>
      [...(data?.priority_queue || [])].sort(
        (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9),
      ),
    [data],
  );
  const criticalCount = priorityAlerts.filter((a) => a.severity === "critical").length;
  const todaysAppointments = data?.todays_appointments || [];

  return (
    <div className="space-y-6 pb-16">
      <PageHeader
        eyebrow="Clinical Command Center"
        title={`Good day, ${doctorDisplayName}`}
        meta={
          loading
            ? "Syncing your clinical priority queue…"
            : `${data?.todays_appointments_count || 0} appointment(s) today · ${data?.active_alerts_count || 0} active triage alert(s)`
        }
        action={
          <button
            type="button"
            onClick={() => navigate("/doctor/patients")}
            className="flex items-center gap-1.5 rounded-full border border-hairline bg-surface-card px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-teal-deep"
          >
            <Users className="h-4 w-4" />
            All patients
          </button>
        }
      />

      <div className="space-y-6 px-5 sm:px-8">
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-clay-alert/30 bg-clay-alert/5 p-4 font-mono text-xs text-clay-alert">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <button type="button" onClick={loadData} className="font-semibold underline">
              Retry
            </button>
          </div>
        )}

        {/* KPI row — all four share one layout */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <KpiCard
            label="Patients"
            value={loading ? "—" : data?.total_patients ?? 0}
            hint="Active panel"
            icon={Users}
            accent="teal"
            onClick={() => navigate("/doctor/patients")}
          />
          <KpiCard
            label="Appts today"
            value={loading ? "—" : data?.todays_appointments_count ?? 0}
            hint="Scheduled visits"
            icon={Calendar}
            accent="indigo"
            onClick={() => navigate("/doctor/appointments")}
          />
          <KpiCard
            label="Labs"
            value={loading ? "—" : data?.pending_labs_count ?? 0}
            hint={data?.pending_labs_count ? "Pending review" : "Nothing pending"}
            icon={Activity}
            accent="teal"
            onClick={() => navigate("/doctor/patients")}
          />
          <KpiCard
            label="Alerts"
            value={loading ? "—" : data?.active_alerts_count ?? 0}
            hint={criticalCount > 0 ? `${criticalCount} critical` : "Priority triage"}
            icon={AlertTriangle}
            accent="clay"
            onClick={() =>
              document.getElementById("priority-triage-section")?.scrollIntoView({ behavior: "smooth" })
            }
          />
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          {/* Priority queue — vertical, severity-sorted, scrollable */}
          <section
            id="priority-triage-section"
            className="flex min-h-0 flex-col rounded-2xl border border-hairline bg-surface-card shadow-xs"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-5 py-4">
              <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
                Needs your attention
              </h2>
              <span
                className={`font-mono text-xs font-semibold ${
                  criticalCount > 0 ? "text-clay-alert" : "text-stone"
                }`}
              >
                {loading
                  ? "Loading…"
                  : priorityAlerts.length === 0
                    ? "All clear"
                    : `${priorityAlerts.length} to review${criticalCount ? ` · ${criticalCount} critical` : ""}`}
              </span>
            </div>

            {loading ? (
              <div className="space-y-3 p-5">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-20 animate-pulse rounded-xl border border-hairline bg-bg-mist" />
                ))}
              </div>
            ) : priorityAlerts.length === 0 ? (
              <div className="flex items-center gap-3 p-5">
                <CheckCircle2 className="h-5 w-5 shrink-0 text-teal-deep" />
                <div>
                  <p className="text-sm font-medium text-ink">No urgent triage alerts</p>
                  <p className="text-xs text-stone">
                    No critical lab or adherence flags are pending across your panel.
                  </p>
                </div>
              </div>
            ) : (
              <ul className="max-h-[560px] divide-y divide-hairline overflow-y-auto">
                {priorityAlerts.map((alert) => {
                  const critical = alert.severity === "critical";
                  return (
                    <li
                      key={alert.id}
                      className={`flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5 ${
                        critical ? "border-l-4 border-l-clay-alert bg-clay-alert/5" : "border-l-4 border-l-transparent"
                      }`}
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate font-display text-base font-semibold text-ink">
                            {alert.patient_name}
                          </span>
                          <span
                            className={`shrink-0 rounded-full px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase ${
                              critical ? "bg-clay-alert text-bg-mist" : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {alert.type}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-ink/80">{alert.title}</p>
                        <p className="line-clamp-2 text-xs leading-relaxed text-stone">{alert.message}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => navigate(`/doctor/patient/${alert.patient_id}`)}
                        className="flex shrink-0 items-center justify-center gap-1 rounded-lg bg-ink px-3.5 py-2 text-xs font-medium text-bg-mist transition-opacity hover:opacity-90"
                      >
                        Review patient
                        <ArrowRight className="h-3 w-3" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Today's appointments */}
          <section className="flex min-h-0 flex-col rounded-2xl border border-hairline bg-surface-card shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-5 py-4">
              <h2 className="font-display text-lg font-semibold tracking-tight text-ink">
                Today's appointments
              </h2>
              <button
                type="button"
                onClick={() => navigate("/doctor/appointments")}
                className="flex items-center gap-1 font-mono text-xs text-stone hover:text-ink"
              >
                Full schedule
                <ExternalLink className="h-3 w-3" />
              </button>
            </div>

            {loading ? (
              <div className="space-y-3 p-5">
                {[1, 2].map((i) => (
                  <div key={i} className="h-14 animate-pulse rounded-xl border border-hairline bg-bg-mist" />
                ))}
              </div>
            ) : todaysAppointments.length === 0 ? (
              <div className="flex items-center gap-3 p-5">
                <Clock className="h-5 w-5 shrink-0 text-stone" />
                <p className="text-sm text-stone">No appointments scheduled for today.</p>
              </div>
            ) : (
              <ul className="max-h-[560px] divide-y divide-hairline overflow-y-auto">
                {todaysAppointments.map((apt) => (
                  <li key={apt.id} className="flex items-center justify-between gap-3 p-4 sm:px-5">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="num w-14 shrink-0 font-mono text-xs font-bold text-teal-deep">
                        {new Date(apt.date_time || apt.appointment_date || Date.now()).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-display text-[15px] font-semibold text-ink">
                          {apt.patient_name}
                        </p>
                        <p className="truncate text-xs text-stone">{apt.reason}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate(`/doctor/patient/${apt.patient_id}`)}
                      className="shrink-0 rounded-lg border border-hairline px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-teal-deep"
                    >
                      Open
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <p className="hidden items-center gap-2 font-mono text-[11px] text-stone sm:flex">
          <Command className="h-3.5 w-3.5 text-teal-deep" />
          Press <kbd className="rounded border border-hairline bg-surface-card px-1.5 py-0.5 font-bold text-ink">Ctrl + K</kbd>{" "}
          anywhere to search patients or launch clinical tools.
        </p>
      </div>
    </div>
  );
};
