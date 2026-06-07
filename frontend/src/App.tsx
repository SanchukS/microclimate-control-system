import { useCallback, useEffect, useMemo, useState, type ComponentType } from 'react'
import axios from 'axios'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import {
  Shield,
  ShieldAlert,
  Factory,
  Thermometer,
  Sun,
  Target,
  Flame,
  Snowflake,
  Wind,
  Trash2,
  Plus,
  Power,
  Settings2,
  AirVent,
  Timer,
  PanelTopOpen,
  PanelTopClose,
} from 'lucide-react'

const API_BASE = 'http://localhost:8000'

type SystemState =
  | 'STANDBY'
  | 'SAFETY_CORRECTION'
  | 'PRE_START'
  | 'WORK_SHIFT'
  | 'PURGING'

interface SystemStatus {
  inside_temp: number
  outside_temp: number
  inflow_temp: number
  heater_temp: number
  cooler_temp: number
  target_temp: number
  heater_power: number
  cooler_power: number
  airflow_power: number
  dampers_open: boolean
  is_manual_mode: boolean
  current_state: SystemState
  t_pre_start: number
}

interface TelemetryLog {
  id: number
  timestamp: string
  inside_temp: number
  outside_temp: number
  inflow_temp: number
  heater_temp: number
  cooler_temp: number
  target_temp: number
  heater_power: number
  cooler_power: number
  airflow_power: number
  dampers_open: boolean
  is_manual_mode: boolean
  current_state: SystemState
  t_pre_start: number
}

interface WorkShift {
  id: number
  start_time: string
  end_time: string
  target_temp: number
}

interface ShiftForm {
  start_time: string
  end_time: string
  target_temp: string
}

const STATE_CONFIG: Record<
  SystemState,
  { label: string; description: string; icon: ComponentType<{ className?: string }>; ring: string; bg: string; text: string }
> = {
  STANDBY: {
    label: 'Энергосбережение / STANDBY',
    description: 'Ожидание, оборудование отключено',
    icon: Shield,
    ring: 'ring-emerald-500/30',
    bg: 'bg-emerald-500/15',
    text: 'text-emerald-300',
  },
  SAFETY_CORRECTION: {
    label: 'Аварийная коррекция ТБ',
    description: 'Коррекция по пределам безопасности',
    icon: ShieldAlert,
    ring: 'ring-red-500/30',
    bg: 'bg-red-500/15',
    text: 'text-red-300',
  },
  PRE_START: {
    label: 'Адаптивный предпуск',
    description: 'Подготовка к началу смены',
    icon: Timer,
    ring: 'ring-amber-500/30',
    bg: 'bg-amber-500/15',
    text: 'text-amber-300',
  },
  WORK_SHIFT: {
    label: 'Рабочая смена',
    description: 'Активный режим производства',
    icon: Factory,
    ring: 'ring-orange-500/30',
    bg: 'bg-orange-500/15',
    text: 'text-orange-300',
  },
  PURGING: {
    label: 'Продувка оборудования',
    description: 'Охлаждение ТЭН / отогрев испарителя',
    icon: Wind,
    ring: 'ring-cyan-500/30',
    bg: 'bg-cyan-500/15',
    text: 'text-cyan-300',
  },
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts)
  return d.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function isShiftActive(start: string, end: string): boolean {
  const now = new Date()
  const nowMin = now.getHours() * 60 + now.getMinutes()
  const startMin = timeToMinutes(start)
  const endMin = timeToMinutes(end)
  if (startMin <= endMin) {
    return nowMin >= startMin && nowMin < endMin
  }
  return nowMin >= startMin || nowMin < endMin
}

function PowerBar({
  label,
  value,
  iconClass,
  barClass,
  icon: Icon,
  equipmentTemp,
}: {
  label: string
  value: number
  iconClass: string
  barClass: string
  icon: ComponentType<{ className?: string }>
  equipmentTemp?: number
}) {
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 text-slate-400">
          <Icon className={`h-4 w-4 ${iconClass}`} />
          {label}
        </span>
        <span className="font-mono text-slate-200">{clamped.toFixed(0)}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-800 ring-1 ring-slate-700/50">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barClass}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {equipmentTemp !== undefined && (
        <p className="text-xs text-slate-500">
          T оборудования:{' '}
          <span className="font-mono text-slate-300">{equipmentTemp.toFixed(1)}°C</span>
        </p>
      )}
    </div>
  )
}

function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
  accent,
  children,
}: {
  label: string
  value: string
  unit?: string
  icon: ComponentType<{ className?: string }>
  accent?: string
  children?: React.ReactNode
}) {
  return (
    <div
      className={`rounded-xl border border-slate-700/60 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm ${accent ?? ''}`}
    >
      <div className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-3xl font-semibold text-slate-50">{value}</span>
        {unit && <span className="text-lg text-slate-500">{unit}</span>}
      </div>
      {children}
    </div>
  )
}

function StateCard({ state }: { state: SystemState | undefined }) {
  const config = state ? STATE_CONFIG[state] : null
  const Icon = config?.icon ?? Shield

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
      <div className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        Режим работы САУ
      </div>
      {config ? (
        <div className="flex items-center gap-3">
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-lg ring-1 ${config.bg} ${config.ring}`}
          >
            <Icon className={`h-6 w-6 ${config.text}`} />
          </div>
          <div>
            <p className={`font-semibold ${config.text}`}>{config.label}</p>
            <p className="text-xs text-slate-500">{config.description}</p>
          </div>
        </div>
      ) : (
        <p className="font-mono text-3xl font-semibold text-slate-50">—</p>
      )}
    </div>
  )
}

function DampersCard({ open }: { open: boolean | undefined }) {
  const isOpen = open === true
  const Icon = isOpen ? PanelTopOpen : PanelTopClose

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
      <div className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
        Заслонки вентиляции
      </div>
      <div className="flex items-center gap-3">
        <div
          className={`flex h-12 w-12 items-center justify-center rounded-lg ring-1 ${
            isOpen
              ? 'bg-emerald-500/15 ring-emerald-500/30'
              : 'bg-slate-700/30 ring-slate-600/40'
          }`}
        >
          <Icon
            className={`h-6 w-6 ${isOpen ? 'text-emerald-400' : 'text-slate-500'}`}
          />
        </div>
        <div>
          <p
            className={`text-lg font-bold tracking-wide ${
              isOpen ? 'text-emerald-400' : 'text-slate-500'
            }`}
          >
            {open === undefined ? '—' : isOpen ? 'ОТКРЫТЫ' : 'ЗАКРЫТЫ'}
          </p>
          <p className="text-xs text-slate-500">
            {isOpen ? 'Приток наружного воздуха' : 'Рециркуляция / изоляция'}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [history, setHistory] = useState<TelemetryLog[]>([])
  const [shifts, setShifts] = useState<WorkShift[]>([])
  const [isManual, setIsManual] = useState(false)
  const [manualHeater, setManualHeater] = useState(0)
  const [manualCooler, setManualCooler] = useState(0)
  const [manualAirflow, setManualAirflow] = useState(0)
  const [shiftForm, setShiftForm] = useState<ShiftForm>({
    start_time: '08:00',
    end_time: '17:00',
    target_temp: '22.0',
  })
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await axios.get<SystemStatus>(`${API_BASE}/api/status`)
      setStatus(data)
      setIsManual(data.is_manual_mode)
      if (!data.is_manual_mode) {
        setManualHeater(data.heater_power)
        setManualCooler(data.cooler_power)
        setManualAirflow(data.airflow_power)
      }
      setError(null)
    } catch {
      setError('Не удалось получить статус системы')
    }
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const { data } = await axios.get<TelemetryLog[]>(`${API_BASE}/api/history`)
      setHistory(data)
    } catch {
      setError('Не удалось загрузить историю')
    }
  }, [])

  const fetchShifts = useCallback(async () => {
    try {
      const { data } = await axios.get<WorkShift[]>(`${API_BASE}/api/shifts`)
      setShifts(data)
    } catch {
      setError('Не удалось загрузить расписание смен')
    }
  }, [])

  useEffect(() => {
    void fetchStatus()
    void fetchHistory()
    void fetchShifts()
  }, [fetchStatus, fetchHistory, fetchShifts])

  useEffect(() => {
    const id = setInterval(() => void fetchStatus(), 2000)
    return () => clearInterval(id)
  }, [fetchStatus])

  useEffect(() => {
    const id = setInterval(() => void fetchHistory(), 5000)
    return () => clearInterval(id)
  }, [fetchHistory])

  const chartData = useMemo(
    () =>
      [...history]
        .reverse()
        .map((log) => ({
          time: formatTimestamp(log.timestamp),
          inside_temp: log.inside_temp,
          outside_temp: log.outside_temp,
          target_temp: log.target_temp,
          inflow_temp: log.inflow_temp,
        })),
    [history],
  )

  const indoorAccent = useMemo(() => {
    if (!status) return ''
    const diff = status.inside_temp - status.target_temp
    if (diff > 0.3) return 'ring-1 ring-blue-500/40 shadow-blue-500/10'
    if (diff < -0.3) return 'ring-1 ring-red-500/40 shadow-red-500/10'
    return 'ring-1 ring-slate-600/40'
  }, [status])

  const indoorGlow = useMemo(() => {
    if (!status) return 'text-slate-50'
    const diff = status.inside_temp - status.target_temp
    if (diff > 0.3) return 'text-blue-400'
    if (diff < -0.3) return 'text-red-400'
    return 'text-slate-50'
  }, [status])

  const handleModeToggle = async (manual: boolean) => {
    setIsManual(manual)
    try {
      if (manual) {
        setManualHeater(status?.heater_power ?? 0)
        setManualCooler(status?.cooler_power ?? 0)
        setManualAirflow(status?.airflow_power ?? 0)
      } else {
        const { data } = await axios.post<SystemStatus>(`${API_BASE}/api/auto`)
        setStatus(data)
        setError(null)
      }
    } catch {
      setError('Не удалось переключить режим')
      setIsManual(!manual)
    }
  }

  const handleApplyManual = async () => {
    setApplying(true)
    try {
      const { data } = await axios.post<SystemStatus>(`${API_BASE}/api/manual`, {
        heater: manualHeater,
        cooler: manualCooler,
        airflow: manualAirflow,
      })
      setStatus(data)
      setError(null)
    } catch {
      setError('Не удалось применить ручное управление')
    } finally {
      setApplying(false)
    }
  }

  const handleAddShift = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await axios.post(`${API_BASE}/api/shifts`, {
        start_time: shiftForm.start_time,
        end_time: shiftForm.end_time,
        target_temp: parseFloat(shiftForm.target_temp),
      })
      await fetchShifts()
      setError(null)
    } catch {
      setError('Не удалось добавить смену (формат времени: HH:MM)')
    }
  }

  const handleDeleteShift = async (id: number) => {
    try {
      await axios.delete(`${API_BASE}/api/shifts/${id}`)
      setShifts((prev) => prev.filter((s) => s.id !== id))
      setError(null)
    } catch {
      setError('Не удалось удалить смену')
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800/20 via-slate-950 to-slate-950" />

      <div className="relative mx-auto max-w-[1600px] px-4 py-6 lg:px-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-50">
              Микроклимат — Панель оператора
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Промышленная САУ с каскадным регулированием и конечным автоматом
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-slate-700/60 bg-slate-900/60 px-4 py-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${status ? 'animate-pulse bg-emerald-500' : 'bg-slate-600'}`}
            />
            <span className="text-sm text-slate-400">
              {status ? 'Связь с контроллером' : 'Ожидание данных…'}
            </span>
          </div>
        </header>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/30 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1fr_380px]">
          <div className="space-y-6">
            <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Температура цеха"
                value={status ? status.inside_temp.toFixed(1) : '—'}
                unit="°C"
                icon={Thermometer}
                accent={indoorAccent}
              >
                <p className={`mt-2 text-xs ${indoorGlow}`}>
                  {status
                    ? status.inside_temp > status.target_temp + 0.3
                      ? 'Охлаждение'
                      : status.inside_temp < status.target_temp - 0.3
                        ? 'Нагрев'
                        : 'В норме'
                    : ''}
                </p>
              </MetricCard>

              <MetricCard
                label="Уличная температура"
                value={status ? status.outside_temp.toFixed(1) : '—'}
                unit="°C"
                icon={Sun}
              />

              <MetricCard
                label="Целевая (уставка)"
                value={status ? status.target_temp.toFixed(1) : '—'}
                unit="°C"
                icon={Target}
              />

              <MetricCard
                label="Температура притока"
                value={status ? status.inflow_temp.toFixed(1) : '—'}
                unit="°C"
                icon={AirVent}
                accent="ring-1 ring-amber-500/30"
              />

              <StateCard state={status?.current_state} />

              <DampersCard open={status?.dampers_open} />

              <MetricCard
                label="Время предпуска"
                value={status ? Math.round(status.t_pre_start).toString() : '—'}
                unit="мин"
                icon={Timer}
              />

              <MetricCard
                label="Ручной режим"
                value={status ? (status.is_manual_mode ? 'ВКЛ' : 'ВЫКЛ') : '—'}
                icon={Settings2}
                accent={
                  status?.is_manual_mode
                    ? 'ring-1 ring-orange-500/40'
                    : 'ring-1 ring-emerald-500/30'
                }
              >
                <p className="mt-2 text-xs text-slate-500">
                  {status?.is_manual_mode ? 'Оператор управляет мощностями' : 'Автомат САУ активен'}
                </p>
              </MetricCard>
            </section>

            <section className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-6 shadow-lg backdrop-blur-sm">
              <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-slate-500">
                История температур
              </h2>
              <div className="h-72 w-full">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis
                        dataKey="time"
                        stroke="#64748b"
                        tick={{ fill: '#94a3b8', fontSize: 11 }}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        stroke="#64748b"
                        tick={{ fill: '#94a3b8', fontSize: 11 }}
                        domain={['auto', 'auto']}
                        unit="°"
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '8px',
                          color: '#e2e8f0',
                        }}
                        labelStyle={{ color: '#94a3b8' }}
                        formatter={(value) =>
                          typeof value === 'number' ? `${value.toFixed(1)}°C` : `${value}`
                        }
                      />
                      <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
                      <Line
                        type="monotone"
                        dataKey="inside_temp"
                        name="Внутри"
                        stroke="#f87171"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="outside_temp"
                        name="Снаружи"
                        stroke="#94a3b8"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="target_temp"
                        name="Уставка"
                        stroke="#4ade80"
                        strokeWidth={2}
                        strokeDasharray="6 4"
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="inflow_temp"
                        name="Температура притока"
                        stroke="#fbbf24"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-slate-500">
                    Загрузка данных графика…
                  </div>
                )}
              </div>
            </section>

            <section className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-6 shadow-lg backdrop-blur-sm">
              <h2 className="mb-5 text-sm font-medium uppercase tracking-wider text-slate-500">
                Мощность оборудования
              </h2>
              <div className="grid gap-5 sm:grid-cols-3">
                <PowerBar
                  label="Нагреватель"
                  value={status?.heater_power ?? 0}
                  iconClass="text-red-500"
                  barClass="bg-red-500"
                  icon={Flame}
                  equipmentTemp={status?.heater_temp}
                />
                <PowerBar
                  label="Охладитель"
                  value={status?.cooler_power ?? 0}
                  iconClass="text-blue-500"
                  barClass="bg-blue-500"
                  icon={Snowflake}
                  equipmentTemp={status?.cooler_temp}
                />
                <PowerBar
                  label="Вентиляция"
                  value={status?.airflow_power ?? 0}
                  iconClass="text-slate-400"
                  barClass="bg-slate-400"
                  icon={Wind}
                />
              </div>
            </section>
          </div>

          <aside className="space-y-6">
            <section className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
              <div className="mb-5 flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-slate-500" />
                <h2 className="text-sm font-medium uppercase tracking-wider text-slate-500">
                  Управление
                </h2>
              </div>

              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/50 px-4 py-3">
                <span className="text-sm text-slate-300">
                  {isManual ? 'Ручное управление' : 'Автоматический режим (САУ)'}
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={isManual}
                  onClick={() => void handleModeToggle(!isManual)}
                  className={`relative h-7 w-12 rounded-full transition-colors ${isManual ? 'bg-orange-600' : 'bg-emerald-600'}`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${isManual ? 'translate-x-5' : 'translate-x-0'}`}
                  />
                </button>
              </label>

              {isManual && (
                <div className="mt-5 space-y-5 border-t border-slate-700/50 pt-5">
                  {(
                    [
                      { label: 'Нагрев', value: manualHeater, set: setManualHeater, color: 'accent-red-500' },
                      { label: 'Охлаждение', value: manualCooler, set: setManualCooler, color: 'accent-blue-500' },
                      { label: 'Вентиляция', value: manualAirflow, set: setManualAirflow, color: 'accent-slate-400' },
                    ] as const
                  ).map(({ label, value, set, color }) => (
                    <div key={label}>
                      <div className="mb-2 flex justify-between text-sm">
                        <span className="text-slate-400">{label}</span>
                        <span className="font-mono text-slate-200">{value.toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        step={1}
                        value={value}
                        onChange={(e) => set(Number(e.target.value))}
                        className={`h-2 w-full cursor-pointer rounded-full bg-slate-700 ${color}`}
                      />
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => void handleApplyManual()}
                    disabled={applying}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-orange-500 disabled:opacity-50"
                  >
                    <Power className="h-4 w-4" />
                    {applying ? 'Применение…' : 'Применить'}
                  </button>
                </div>
              )}
            </section>

            <section className="rounded-xl border border-slate-700/60 bg-slate-900/80 p-5 shadow-lg backdrop-blur-sm">
              <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-slate-500">
                Расписание смен
              </h2>

              <div className="mb-4 overflow-hidden rounded-lg border border-slate-700/50">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/50 bg-slate-800/50 text-left text-xs uppercase tracking-wider text-slate-500">
                      <th className="px-3 py-2">Старт</th>
                      <th className="px-3 py-2">Конец</th>
                      <th className="px-3 py-2">°C</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {shifts.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-3 py-4 text-center text-slate-500">
                          Смены не заданы
                        </td>
                      </tr>
                    )}
                    {shifts.map((shift) => (
                      <tr
                        key={shift.id}
                        className={`border-b border-slate-800/80 last:border-0 ${isShiftActive(shift.start_time, shift.end_time) ? 'bg-orange-500/5' : ''}`}
                      >
                        <td className="px-3 py-2.5 font-mono text-slate-300">{shift.start_time}</td>
                        <td className="px-3 py-2.5 font-mono text-slate-300">{shift.end_time}</td>
                        <td className="px-3 py-2.5 font-mono text-slate-300">
                          {shift.target_temp.toFixed(1)}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <button
                            type="button"
                            onClick={() => void handleDeleteShift(shift.id)}
                            className="rounded p-1.5 text-slate-500 transition hover:bg-red-500/10 hover:text-red-400"
                            title="Удалить смену"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <form onSubmit={(e) => void handleAddShift(e)} className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
                  Добавить смену
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">Старт</label>
                    <input
                      type="time"
                      value={shiftForm.start_time}
                      onChange={(e) =>
                        setShiftForm((f) => ({ ...f, start_time: e.target.value }))
                      }
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-orange-500/50"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">Конец</label>
                    <input
                      type="time"
                      value={shiftForm.end_time}
                      onChange={(e) =>
                        setShiftForm((f) => ({ ...f, end_time: e.target.value }))
                      }
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-orange-500/50"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">Целевая температура</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="40"
                    value={shiftForm.target_temp}
                    onChange={(e) =>
                      setShiftForm((f) => ({ ...f, target_temp: e.target.value }))
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-orange-500/50"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-slate-700"
                >
                  <Plus className="h-4 w-4" />
                  Добавить смену
                </button>
              </form>
            </section>
          </aside>
        </div>
      </div>
    </div>
  )
}
