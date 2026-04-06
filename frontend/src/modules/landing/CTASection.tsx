import { motion } from 'motion/react';
import { Link } from 'react-router';
import { Sparkles } from 'lucide-react';

export function CTASection() {
  return (
    <section className="py-24 relative overflow-hidden">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="bg-blue-600 rounded-[3rem] p-10 md:p-16 text-center text-white shadow-2xl shadow-blue-600/30 overflow-hidden relative"
        >
          <div className="absolute top-[-20%] right-[-10%] w-[50%] h-[150%] bg-blue-500 rounded-full blur-[80px]" />
          <div className="relative z-10">
            <h2 className="text-3xl md:text-5xl font-bold mb-6">Готовы к приключениям?</h2>
            <p className="text-blue-100 text-lg md:text-xl max-w-2xl mx-auto mb-10">
              Забудьте о долгих часах поиска информации. Позвольте Odyssey AI составить идеальный
              план специально для вас.
            </p>
            <Link
              to="/chat"
              className="inline-flex items-center gap-2 px-8 py-4 rounded-full font-bold text-blue-600 bg-white hover:bg-slate-50 transition-all hover:scale-105 shadow-xl text-lg"
            >
              Начать сейчас <Sparkles size={20} />
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
