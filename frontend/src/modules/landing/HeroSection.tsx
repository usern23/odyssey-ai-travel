import { motion } from 'motion/react';
import { Link } from 'react-router';
import { Sparkles, MapPin, Calendar, Compass, ArrowRight } from 'lucide-react';

export function HeroSection() {
  return (
    <section className="relative pt-20 pb-32 lg:pt-32 lg:pb-40 px-4 sm:px-6 lg:px-8 flex flex-col items-center justify-center text-center min-h-[85vh] overflow-hidden">
      {/* Background Gradients */}
      <div className="absolute top-0 w-full h-full overflow-hidden -z-10 pointer-events-none">
        <div className="absolute top-[-10%] left-[20%] w-[50%] h-[50%] rounded-full bg-blue-400/20 dark:bg-blue-600/20 blur-[120px]" />
        <div className="absolute bottom-[10%] right-[10%] w-[40%] h-[40%] rounded-full bg-indigo-400/20 dark:bg-indigo-600/20 blur-[120px]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
        className="max-w-4xl mx-auto z-10"
      >
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 text-sm font-semibold mb-8 border border-blue-100 dark:border-blue-500/20">
          <Sparkles size={16} />
          Odyssey AI — Планировщик путешествий
        </div>

        <h1 className="text-5xl lg:text-7xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-8 leading-[1.1]">
          Идеальное путешествие <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-500 dark:from-blue-400 dark:to-indigo-400">
            за пару минут
          </span>
        </h1>

        <p className="text-lg lg:text-xl text-slate-600 dark:text-slate-300 mb-10 max-w-2xl mx-auto leading-relaxed">
          Просто расскажите, куда вы хотите поехать и что любите делать. Odyssey AI создаст
          детальный маршрут на каждый день.
        </p>

        <Link
          to="/chat"
          className="inline-flex items-center gap-2 px-8 py-4 rounded-2xl font-bold text-white bg-blue-600 hover:bg-blue-700 shadow-xl shadow-blue-600/20 transition-all hover:-translate-y-1 text-lg"
        >
          Спланировать маршрут
          <ArrowRight size={20} />
        </Link>
      </motion.div>

      {/* Feature Cards */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.3 }}
        className="w-full max-w-5xl mx-auto mt-20 grid grid-cols-1 md:grid-cols-3 gap-6 relative z-10"
      >
        {[
          { icon: <MapPin className="text-blue-500" size={24} />, title: 'Умные маршруты', desc: 'Оптимизация логистики на каждый день' },
          { icon: <Compass className="text-indigo-500" size={24} />, title: 'Скрытые места', desc: 'Рекомендации не только для туристов' },
          { icon: <Calendar className="text-teal-500" size={24} />, title: 'Гибкий график', desc: 'Легко меняйте планы в любой момент' },
        ].map((feature, i) => (
          <div
            key={i}
            className="bg-white/60 dark:bg-slate-900/60 backdrop-blur-xl border border-slate-200 dark:border-slate-800 p-6 rounded-3xl shadow-lg shadow-slate-200/20 dark:shadow-none hover:bg-white dark:hover:bg-slate-900 transition-colors text-left"
          >
            <div className="w-12 h-12 rounded-xl bg-slate-50 dark:bg-slate-800 flex items-center justify-center mb-4 border border-slate-100 dark:border-slate-700">
              {feature.icon}
            </div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">
              {feature.title}
            </h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
              {feature.desc}
            </p>
          </div>
        ))}
      </motion.div>
    </section>
  );
}
