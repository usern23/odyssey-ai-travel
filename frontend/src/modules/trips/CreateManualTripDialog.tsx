import { useState } from 'react';
import { useNavigate } from 'react-router';
import { X } from 'lucide-react';
import { api, ApiError } from '@/shared/api';
import DateRangePicker from './DateRangePicker';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CreateManualTripDialog({ open, onClose }: Props) {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [destination, setDestination] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [startHour, setStartHour] = useState('10');
  const [endHour, setEndHour] = useState('22');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const submit = async () => {
    if (!name.trim()) { setError('Укажите название поездки'); return; }
    if (!destination.trim()) { setError('Укажите город или страну'); return; }
    const sh = parseInt(startHour, 10);
    const eh = parseInt(endHour, 10);
    if (Number.isNaN(sh) || sh < 0 || sh > 23) { setError('Час старта должен быть от 0 до 23'); return; }
    if (Number.isNaN(eh) || eh < 1 || eh > 24) { setError('Час окончания должен быть от 1 до 24'); return; }
    if (eh <= sh) { setError('Час окончания должен быть больше часа старта'); return; }
    setSubmitting(true);
    setError(null);
    try {
      const trip = await api.createManualTrip({
        name: name.trim(),
        destination: destination.trim(),
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        // Hotel is optional — backend geocodes `destination` and uses
        // the city centre as a placeholder starting point.
        start_hour: sh,
        end_hour: eh,
      });
      onClose();
      navigate(`/trips/${trip.id}/edit`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Не удалось создать поездку';
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-2xl my-8 overflow-visible">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Новая поездка вручную</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={20} />
          </button>
        </div>
        <div className="p-6 space-y-3">
          {error && (
            <div className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{error}</div>
          )}
          <Field label="Название" value={name} onChange={setName} placeholder="Манчестер 3 дня" />
          <Field label="Город / страна *" value={destination} onChange={setDestination} placeholder="Manchester" />
          <DateRangePicker
            startDate={startDate}
            endDate={endDate}
            onChange={(s, e) => { setStartDate(s); setEndDate(e); }}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Час старта дня" type="number" value={startHour} onChange={setStartHour} placeholder="10" min={0} max={23} />
            <Field label="Час окончания дня" type="number" value={endHour} onChange={setEndHour} placeholder="22" min={1} max={24} />
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Стартовую точку (отель) можно будет добавить позже в редакторе.
            До этого по умолчанию используется центр города.
          </p>
        </div>
        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800">
            Отмена
          </button>
          <button onClick={submit} disabled={submitting}
                  className="px-4 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
            {submitting ? 'Создаю…' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = 'text', min, max }: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; type?: string; min?: number; max?: number;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        min={min}
        max={max}
        className="w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
      />
    </label>
  );
}
