import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plane,
  ChevronRight,
  ChevronLeft,
  Mountain,
  Waves,
  Building2,
  TreePine,
  Sun,
  Home,
  Check,
} from 'lucide-react';
import { api, ApiError, type UserProfile } from '@/shared/api';
import { useAuth } from '@/modules/auth';

const STEPS = [
  'activity',
  'budget',
  'categories',
  'landscape',
  'food',
  'schedule',
] as const;

type Step = (typeof STEPS)[number];

const ACTIVITY_OPTIONS = [
  {
    value: 'calm',
    label: 'Спокойный',
    desc: '4–5 мест в день, прогулки без спешки',
    emoji: '🧘',
  },
  {
    value: 'moderate',
    label: 'Умеренный',
    desc: '6–8 мест в день, баланс отдыха и впечатлений',
    emoji: '🚶',
  },
  {
    value: 'active',
    label: 'Насыщенный',
    desc: '8–10 мест в день, максимум впечатлений',
    emoji: '🏃',
  },
];

const BUDGET_OPTIONS = [
  {
    value: 'economy',
    label: 'Экономный',
    desc: 'Бесплатные достопримечательности, бюджетные кафе',
    emoji: '💰',
  },
  {
    value: 'comfort',
    label: 'Комфортный',
    desc: 'Музеи, хорошие рестораны, экскурсии',
    emoji: '💳',
  },
  {
    value: 'unlimited',
    label: 'Без ограничений',
    desc: 'Лучшие места без оглядки на бюджет',
    emoji: '💎',
  },
];

const CATEGORY_LABELS: Record<string, { label: string; emoji: string }> = {
  museum: { label: 'Музеи', emoji: '🏛️' },
  landmark: { label: 'Достопримечательности', emoji: '🗽' },
  park: { label: 'Парки', emoji: '🌳' },
  restaurant: { label: 'Рестораны', emoji: '🍽️' },
  cafe: { label: 'Кафе', emoji: '☕' },
  religious: { label: 'Храмы и соборы', emoji: '⛪' },
  entertainment: { label: 'Развлечения', emoji: '🎡' },
  shopping: { label: 'Шоппинг', emoji: '🛍️' },
  nightlife: { label: 'Ночная жизнь', emoji: '🌙' },
  nature: { label: 'Природа', emoji: '🌿' },
  viewpoint: { label: 'Смотровые', emoji: '🔭' },
  beach: { label: 'Пляжи', emoji: '🏖️' },
};

const LANDSCAPE_ICONS: Record<string, { label: string; Icon: typeof Mountain }> = {
  sea: { label: 'Море', Icon: Waves },
  mountains: { label: 'Горы', Icon: Mountain },
  city: { label: 'Город', Icon: Building2 },
  village: { label: 'Деревня', Icon: Home },
  forest: { label: 'Лес', Icon: TreePine },
  desert: { label: 'Пустыня', Icon: Sun },
};

const FOOD_OPTIONS = [
  { key: 'vegetarian', label: 'Вегетарианская кухня', emoji: '🥬' },
  { key: 'halal', label: 'Халяль', emoji: '🍖' },
  { key: 'local_cuisine', label: 'Местная кухня', emoji: '🍜' },
  { key: 'street_food', label: 'Уличная еда', emoji: '🌮' },
];

interface QuestionnairePageProps {
  editMode?: boolean;
}

export default function QuestionnairePage({ editMode = false }: QuestionnairePageProps) {
  const [searchParams] = useSearchParams();
  const isEdit = editMode || searchParams.get('edit') === 'true';

  const [step, setStep] = useState(0);
  const [activityLevel, setActivityLevel] = useState('moderate');
  const [budgetLevel, setBudgetLevel] = useState('comfort');
  const [categories, setCategories] = useState<Record<string, number>>({
    museum: 5, landmark: 5, park: 5, restaurant: 5, cafe: 5, religious: 5,
    entertainment: 5, shopping: 5, nightlife: 5, nature: 5, viewpoint: 5, beach: 5,
  });
  const [landscape, setLandscape] = useState<Record<string, number>>({
    sea: 5, mountains: 5, city: 5, village: 5, forest: 5, desert: 5,
  });
  const [food, setFood] = useState<Record<string, boolean>>({
    vegetarian: false, halal: false, local_cuisine: true, street_food: false,
  });
  const [startHour, setStartHour] = useState<number>(10);
  const [endHour, setEndHour] = useState<number>(22);
  const [mealCount, setMealCount] = useState<number>(2);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) navigate('/login');
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (!isEdit) return;
    api.getProfile().then((p) => {
      setActivityLevel(p.activity_level);
      setBudgetLevel(p.budget_level);
      setCategories(p.category_preferences);
      setLandscape(p.landscape_preferences);
      setFood(p.food_preferences);
      if (typeof p.start_hour === 'number') setStartHour(p.start_hour);
      if (typeof p.end_hour === 'number') setEndHour(p.end_hour);
      if (typeof p.meal_count_per_day === 'number') setMealCount(p.meal_count_per_day);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [isEdit]);

  const currentStep = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const buildPayload = (): Partial<UserProfile> => ({
    activity_level: activityLevel,
    budget_level: budgetLevel,
    category_preferences: categories,
    landscape_preferences: landscape,
    food_preferences: food,
    start_hour: startHour,
    end_hour: endHour,
    meal_count_per_day: mealCount,
  });

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const payload = buildPayload();
      if (isEdit) {
        await api.updateProfile(payload);
      } else {
        await api.createProfile(payload);
      }
      navigate('/chat');
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        // Profile already exists, try update
        try {
          await api.updateProfile(buildPayload());
          navigate('/chat');
        } catch {
          setSaving(false);
        }
      } else {
        setSaving(false);
      }
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-black flex items-center justify-center">
        <div className="text-slate-400">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black text-slate-900 dark:text-white flex flex-col items-center justify-center p-4 relative overflow-hidden font-sans">
      {/* Background blurs */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-500/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-indigo-500/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Progress */}
      <div className="w-full max-w-lg mb-8 relative z-10">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
            Шаг {step + 1} из {STEPS.length}
          </span>
          {isEdit && (
            <button onClick={() => navigate(-1)} className="text-sm text-blue-600 hover:underline">
              Отмена
            </button>
          )}
        </div>
        <div className="h-2 bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-blue-600 rounded-full"
            initial={false}
            animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>

      {/* Card */}
      <motion.div
        key={currentStep}
        initial={{ opacity: 0, x: 30 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -30 }}
        transition={{ duration: 0.3 }}
        className="w-full max-w-lg bg-white dark:bg-[#121212] border border-slate-200 dark:border-[#1A1A1A] p-8 rounded-[2rem] relative z-10 shadow-2xl shadow-blue-900/5 dark:shadow-none"
      >
        {/* Header icon */}
        {step === 0 && !isEdit && (
          <div className="flex justify-center mb-6">
            <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
              <Plane fill="currentColor" size={24} className="ml-1 mt-1" />
            </div>
          </div>
        )}

        <AnimatePresence mode="wait">
          {currentStep === 'activity' && (
            <StepContent title="Какой темп путешествия вам ближе?">
              <div className="space-y-3">
                {ACTIVITY_OPTIONS.map((opt) => (
                  <OptionCard
                    key={opt.value}
                    selected={activityLevel === opt.value}
                    onClick={() => setActivityLevel(opt.value)}
                    emoji={opt.emoji}
                    label={opt.label}
                    desc={opt.desc}
                  />
                ))}
              </div>
            </StepContent>
          )}

          {currentStep === 'budget' && (
            <StepContent title="Какой у вас бюджет на путешествие?">
              <div className="space-y-3">
                {BUDGET_OPTIONS.map((opt) => (
                  <OptionCard
                    key={opt.value}
                    selected={budgetLevel === opt.value}
                    onClick={() => setBudgetLevel(opt.value)}
                    emoji={opt.emoji}
                    label={opt.label}
                    desc={opt.desc}
                  />
                ))}
              </div>
            </StepContent>
          )}

          {currentStep === 'categories' && (
            <StepContent title="Что вам интересно?">
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                Передвиньте слайдер — 0 (не интересно) ... 10 (обожаю)
              </p>
              <div className="space-y-4 max-h-[50vh] overflow-y-auto pr-2">
                {Object.entries(CATEGORY_LABELS).map(([key, { label, emoji }]) => (
                  <SliderRow
                    key={key}
                    emoji={emoji}
                    label={label}
                    value={categories[key] ?? 5}
                    onChange={(v) => setCategories((prev) => ({ ...prev, [key]: v }))}
                  />
                ))}
              </div>
            </StepContent>
          )}

          {currentStep === 'landscape' && (
            <StepContent title="Какая обстановка вам нравится?">
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-1 italic">
                Используется для подбора направлений поездки
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                0 — совсем не привлекает, 10 — идеально
              </p>
              <div className="space-y-5">
                {Object.entries(LANDSCAPE_ICONS).map(([key, { label, Icon }]) => (
                  <div key={key} className="flex items-center gap-3">
                    <Icon size={20} className="text-blue-500 shrink-0" />
                    <span className="w-24 text-sm font-medium">{label}</span>
                    <input
                      type="range"
                      min={0}
                      max={10}
                      value={landscape[key] ?? 5}
                      onChange={(e) =>
                        setLandscape((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                      }
                      className="flex-1 accent-blue-600"
                    />
                    <span className="w-6 text-center text-sm font-mono text-slate-500">
                      {landscape[key] ?? 5}
                    </span>
                  </div>
                ))}
              </div>
            </StepContent>
          )}

          {currentStep === 'food' && (
            <StepContent title="Предпочтения в еде">
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-4 italic">
                Влияет на выбор кафе/ресторанов в плане и на подбор направлений
              </p>
              <div className="space-y-3">
                {FOOD_OPTIONS.map(({ key, label, emoji }) => (
                  <button
                    key={key}
                    onClick={() => setFood((prev) => ({ ...prev, [key]: !prev[key] }))}
                    className={`w-full flex items-center gap-3 px-5 py-4 rounded-2xl border transition-all text-left ${
                      food[key]
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
                        : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                    }`}
                  >
                    <span className="text-xl">{emoji}</span>
                    <span className="flex-1 font-medium text-sm">{label}</span>
                    {food[key] && <Check size={18} className="text-blue-600" />}
                  </button>
                ))}
              </div>
            </StepContent>
          )}

          {currentStep === 'schedule' && (
            <StepContent title="Режим дня">
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                Настройте, когда начинается ваш активный день и сколько раз вые любите есть.
              </p>
              <div className="space-y-8">
                <div>
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-sm font-medium">🌅 Начало дня</span>
                    <span className="text-lg font-mono font-semibold text-blue-600">
                      {String(startHour).padStart(2, '0')}:00
                    </span>
                  </div>
                  <input
                    type="range"
                    min={7}
                    max={12}
                    step={1}
                    value={startHour}
                    onChange={(e) => setStartHour(Number(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>07:00</span>
                    <span>12:00</span>
                  </div>
                </div>
                <div>
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-sm font-medium">🌙 Конец дня</span>
                    <span className="text-lg font-mono font-semibold text-blue-600">
                      {String(endHour).padStart(2, '0')}:00
                    </span>
                  </div>
                  <input
                    type="range"
                    min={Math.max(14, startHour + 4)}
                    max={24}
                    step={1}
                    value={Math.max(endHour, Math.max(14, startHour + 4))}
                    onChange={(e) => setEndHour(Number(e.target.value))}
                    className="w-full accent-blue-600"
                  />
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>{String(Math.max(14, startHour + 4)).padStart(2, '0')}:00</span>
                    <span>24:00</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-2">
                    Чем позже заканчивается день — тем больше мест помещается в маршрут.
                  </p>
                </div>
                <div>
                  <div className="flex items-baseline justify-between mb-3">
                    <span className="text-sm font-medium">🍽️ Приёмов пищи в день</span>
                    <span className="text-lg font-mono font-semibold text-blue-600">{mealCount}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[1, 2, 3].map((n) => (
                      <button
                        key={n}
                        onClick={() => setMealCount(n)}
                        className={`px-4 py-3 rounded-xl border text-sm font-medium transition-all ${
                          mealCount === n
                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 ring-2 ring-blue-500/20'
                            : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'
                        }`}
                      >
                        {n === 1 ? '1 — обед' : n === 2 ? '2 — обед + ужин' : '3 — завтрак/обед/ужин'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </StepContent>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Navigation */}
      <div className="flex items-center justify-between w-full max-w-lg mt-6 relative z-10">
        <button
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
          className="flex items-center gap-1 px-4 py-2.5 text-sm font-medium text-slate-500 hover:text-slate-800 dark:hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft size={18} /> Назад
        </button>

        {isLast ? (
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex items-center gap-2 px-8 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-500/20 disabled:opacity-60"
          >
            {saving ? 'Сохраняю...' : isEdit ? 'Сохранить' : 'Начать путешествие'}
          </button>
        ) : (
          <button
            onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
            className="flex items-center gap-1 px-6 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-sm"
          >
            Далее <ChevronRight size={18} />
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────── */

function StepContent({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-xl font-bold mb-5 text-center">{title}</h2>
      {children}
    </div>
  );
}

function OptionCard({
  selected,
  onClick,
  emoji,
  label,
  desc,
}: {
  selected: boolean;
  onClick: () => void;
  emoji: string;
  label: string;
  desc: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-4 px-5 py-4 rounded-2xl border transition-all text-left ${
        selected
          ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10 ring-2 ring-blue-500/20'
          : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
      }`}
    >
      <span className="text-2xl">{emoji}</span>
      <div>
        <div className="font-semibold text-sm">{label}</div>
        <div className="text-xs text-slate-500 dark:text-slate-400">{desc}</div>
      </div>
      {selected && (
        <Check size={18} className="ml-auto text-blue-600 shrink-0" />
      )}
    </button>
  );
}

function SliderRow({
  emoji,
  label,
  value,
  onChange,
}: {
  emoji: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-lg">{emoji}</span>
      <span className="w-40 text-sm font-medium truncate">{label}</span>
      <input
        type="range"
        min={0}
        max={10}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 accent-blue-600"
      />
      <span className="w-6 text-center text-sm font-mono text-slate-500">{value}</span>
    </div>
  );
}
