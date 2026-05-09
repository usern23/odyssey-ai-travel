import { useState, useEffect, useRef } from 'react';
import { DayPicker, type DateRange } from 'react-day-picker';
import { format, isValid, parse } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Calendar as CalendarIcon } from 'lucide-react';
import 'react-day-picker/dist/style.css';

interface Props {
  startDate: string;          // ISO yyyy-MM-dd or ''
  endDate: string;            // ISO yyyy-MM-dd or ''
  onChange: (start: string, end: string) => void;
}

const ISO = 'yyyy-MM-dd';
const HUMAN = 'dd.MM.yyyy';

function isoToDate(iso: string): Date | undefined {
  if (!iso) return undefined;
  const d = parse(iso, ISO, new Date());
  return isValid(d) ? d : undefined;
}

function dateToIso(d: Date | undefined): string {
  return d ? format(d, ISO) : '';
}

function humanFromIso(iso: string): string {
  const d = isoToDate(iso);
  return d ? format(d, HUMAN) : '';
}

function isoFromHuman(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return '';
  const d = parse(trimmed, HUMAN, new Date());
  if (!isValid(d)) return null;
  return format(d, ISO);
}

export default function DateRangePicker({ startDate, endDate, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [startText, setStartText] = useState(humanFromIso(startDate));
  const [endText, setEndText] = useState(humanFromIso(endDate));
  const popRef = useRef<HTMLDivElement | null>(null);

  // Sync when external value changes (e.g., clearing).
  useEffect(() => { setStartText(humanFromIso(startDate)); }, [startDate]);
  useEffect(() => { setEndText(humanFromIso(endDate)); }, [endDate]);

  // Close on outside click or escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!popRef.current) return;
      if (!popRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const range: DateRange = {
    from: isoToDate(startDate),
    to: isoToDate(endDate),
  };

  const handleSelect = (r: DateRange | undefined) => {
    const s = dateToIso(r?.from);
    const e = dateToIso(r?.to);
    onChange(s, e);
    setStartText(humanFromIso(s));
    setEndText(humanFromIso(e));
    if (r?.from && r?.to) setOpen(false);
  };

  const commitStart = () => {
    const iso = isoFromHuman(startText);
    if (iso === null) { setStartText(humanFromIso(startDate)); return; }
    onChange(iso, endDate);
  };
  const commitEnd = () => {
    const iso = isoFromHuman(endText);
    if (iso === null) { setEndText(humanFromIso(endDate)); return; }
    onChange(startDate, iso);
  };

  const summary =
    startDate && endDate
      ? `${humanFromIso(startDate)} — ${humanFromIso(endDate)}`
      : startDate
        ? `c ${humanFromIso(startDate)}`
        : 'Выберите даты';

  return (
    <div className="relative" ref={popRef}>
      <span className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
        Даты поездки
      </span>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm text-left text-slate-900 dark:text-white hover:border-slate-400 dark:hover:border-slate-600 focus:ring-2 focus:ring-blue-500 outline-none"
      >
        <CalendarIcon size={16} className="text-slate-400 flex-shrink-0" />
        <span className={startDate ? '' : 'text-slate-400'}>{summary}</span>
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-2xl p-3 max-h-[70vh] overflow-auto">
          <div className="flex gap-2 mb-3">
            <label className="flex-1 min-w-0">
              <span className="block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Начало</span>
              <input
                type="text"
                value={startText}
                onChange={(e) => setStartText(e.target.value)}
                onBlur={commitStart}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitStart(); } }}
                placeholder="дд.мм.гггг"
                className="w-full px-2 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
              />
            </label>
            <label className="flex-1 min-w-0">
              <span className="block text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1">Конец</span>
              <input
                type="text"
                value={endText}
                onChange={(e) => setEndText(e.target.value)}
                onBlur={commitEnd}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); commitEnd(); } }}
                placeholder="дд.мм.гггг"
                className="w-full px-2 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm text-slate-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500"
              />
            </label>
          </div>
          <DayPicker
            mode="range"
            numberOfMonths={2}
            locale={ru}
            selected={range}
            onSelect={handleSelect}
            defaultMonth={range.from ?? new Date()}
            weekStartsOn={1}
            showOutsideDays
            className="odyssey-rdp odyssey-rdp-compact"
          />
          <div className="flex justify-between items-center pt-2 mt-1 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => onChange('', '')}
              className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            >
              Очистить
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-xs px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
            >
              Готово
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
